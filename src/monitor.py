"""Monitoring: is the incoming data, or the model's accuracy on it, moving away from training?

Run from repo root:
  python src/monitor.py --current demo_data/normal_orders.csv       # exit 0  no drift
  python src/monitor.py --current demo_data/drift_north.csv         # exit 2  Data Drift
  python src/monitor.py --current demo_data/drift_blackfriday.csv   # exit 3  Concept Drift
  python src/monitor.py --current <csv> --api-url http://localhost:8000   # also read the API's /metrics

Reference = train split. Thresholds are the constants below (same numbers as docs/monitoring.md):
  Data Drift     PSI > 0.2 on total_weight_g or distance_km. Inputs moved; needs no labels.
  Concept Drift  MAE of @champion on the current file > test MAE + 2 days while the inputs did NOT
                 drift: the same kind of orders now take longer, so the input -> target relation changed.
                 (MAE over the limit together with drifted inputs is reported as Data Drift.)
  Retrain        Data Drift, or daily MAE over the limit on 2 consecutive days -> python src/pipeline.py
KS p-value is printed for information only: with 66k reference rows it flags even normal data.
Every finding goes to alerts.send_alert (Slack, or logs/alerts.log). HTML report: reports/ (gitignored).
"""
import argparse
import json
import os
import sys
from urllib.request import urlopen

import mlflow
import numpy as np
import pandas as pd
from evidently import Report
from evidently.metrics import ValueDrift
from mlflow.exceptions import MlflowException
from sklearn.metrics import mean_absolute_error

from alerts import send_alert
from features import add_features
from schema import input_schema
from train import MODEL_NAME, TARGET, TRACKING_URI, load_splits, xy

DRIFT_COLUMNS = ['total_weight_g', 'distance_km']        # these decide Data Drift (GUIDE contract D)
INFO_COLUMNS = ['total_price', 'total_freight', TARGET]  # shown in the report, do not decide
PSI_LIMIT = 0.2
KS_P_LIMIT = 0.01
MAE_MARGIN = 2.0         # days: MAE limit = test MAE + this
RETRAIN_DAYS = 2         # consecutive days over the MAE limit before retraining
MIN_ORDERS_PER_DAY = 30  # a day with fewer orders is too noisy to judge
P95_LIMIT_MS = 200       # SLO, same as docs/serving-metrics.md
ERROR_RATE_LIMIT = 0.01
OUT_DIR = 'reports'
EXIT_OK, EXIT_DATA_DRIFT, EXIT_CONCEPT_DRIFT = 0, 2, 3


def load_current(path: str):
    """Same cleaning as load_splits: drop missing coordinates, validate with the schema."""
    raw = pd.read_csv(path).dropna(subset=['customer_lat', 'seller_lat'])
    return input_schema.validate(raw), raw[TARGET]


def feature_drift(reference: pd.DataFrame, current: pd.DataFrame, html_path: str) -> dict:
    """PSI and KS p-value per column with Evidently -> {column: (psi, ks_p)}. Saves the HTML report."""
    columns = DRIFT_COLUMNS + INFO_COLUMNS
    metrics = []
    for col in columns:
        metrics += [ValueDrift(column=col, method='psi', threshold=PSI_LIMIT),
                    ValueDrift(column=col, method='ks', threshold=KS_P_LIMIT)]
    snapshot = Report(metrics).run(current[columns], reference[columns])  # current first, reference second
    snapshot.save_html(html_path)
    values = [m['value'] for m in snapshot.dict()['metrics']]  # same order as metrics: psi, ks, psi, ks, ...
    return {col: (values[2 * i], values[2 * i + 1]) for i, col in enumerate(columns)}


def days_over_limit(X: pd.DataFrame, y: pd.Series, pred: np.ndarray, limit: float):
    """MAE per purchase day -> (days judged, longest run of consecutive days with MAE > limit)."""
    errors = pd.DataFrame({'day': X['order_purchase_timestamp'].dt.normalize().to_numpy(),
                           'error': np.abs(pred - y.to_numpy())})
    daily = errors.groupby('day')['error'].agg(['mean', 'size'])
    daily = daily[daily['size'] >= MIN_ORDERS_PER_DAY]
    longest = streak = 0
    previous = None
    for day, mae in daily['mean'].items():
        next_day = previous is not None and (day - previous).days == 1
        streak = (streak + 1 if next_day else 1) if mae > limit else 0
        longest = max(longest, streak)
        previous = day
    return len(daily), longest


def system_status(api_url: str) -> None:
    """Compare the API's own /metrics with the SLO. Only alerts, never changes the exit code."""
    try:
        with urlopen(api_url.rstrip('/') + '/metrics', timeout=5) as response:
            m = json.load(response)
    except (OSError, ValueError) as e:  # API not running = skip, drift result still counts
        print(f'\nsystem: cannot read {api_url}/metrics ({e}), skipped')
        return
    p95 = m['latency_ms']['p95']
    error_rate = m['errors_total'] / max(m['requests_total'], 1)
    broken = p95 > P95_LIMIT_MS or error_rate >= ERROR_RATE_LIMIT
    summary = (f'P95={p95:.1f} ms (limit {P95_LIMIT_MS}), error rate={error_rate:.2%} (limit {ERROR_RATE_LIMIT:.0%}), '
               f'requests={m["requests_total"]}, rejected={m["rejected_total"]}, model v{m["model_version"]}')
    print(f'\nsystem: {summary}  {"SLO BREACHED" if broken else "ok"}')
    if broken:
        send_alert('API SLO breached', summary)


def main(current_path: str, api_url: str | None = None) -> int:
    mlflow.set_tracking_uri(TRACKING_URI)
    try:
        model = mlflow.sklearn.load_model(f'models:/{MODEL_NAME}@champion')
    except MlflowException as e:
        sys.exit(f'no @champion model: run src/train.py then src/registry.py promote first ({e})')

    train, _, test = load_splits()
    X, y = load_current(current_path)
    name = os.path.splitext(os.path.basename(current_path))[0]
    os.makedirs(OUT_DIR, exist_ok=True)
    html_path = f'{OUT_DIR}/monitor_{name}.html'
    print(f'\ncurrent = {current_path} (rows={len(X)})   reference = train split (rows={len(train)})')

    # 1) Data Drift: did the inputs move away from the train split?
    drift = feature_drift(add_features(train), add_features(X).assign(**{TARGET: y}), html_path)
    drifted = [col for col in DRIFT_COLUMNS if drift[col][0] > PSI_LIMIT]
    print(f'  {"column":<16} {"PSI":>7} {"KS p-value":>11}  result')
    for col, (psi, ks_p) in drift.items():
        result = ('DRIFT' if col in drifted else 'ok') if col in DRIFT_COLUMNS else 'info'
        print(f'  {col:<16} {psi:>7.3f} {ks_p:>11.4f}  {result}')

    # 2) Concept Drift: is @champion less accurate here than on the normal test split?
    X_test, y_test = xy(test)
    test_mae = mean_absolute_error(y_test, model.predict(X_test))
    limit = test_mae + MAE_MARGIN
    pred = model.predict(X)
    mae = mean_absolute_error(y, pred)
    mae_over = mae > limit
    n_days, streak = days_over_limit(X, y, pred, limit)
    print(f'  MAE={mae:.3f} days   test MAE={test_mae:.3f}   limit={limit:.3f}  {"OVER LIMIT" if mae_over else "ok"}')
    print(f'  daily MAE: {n_days} days with >= {MIN_ORDERS_PER_DAY} orders, '
          f'longest run over the limit = {streak} days (retrain at {RETRAIN_DAYS})')

    # 3) Verdict. Data Drift wins over MAE: when the inputs moved, a higher MAE is explained by them.
    if drifted:
        code, verdict = EXIT_DATA_DRIFT, 'Data Drift'
    elif mae_over:
        code, verdict = EXIT_CONCEPT_DRIFT, 'Concept Drift'
    else:
        code, verdict = EXIT_OK, 'no drift'
    retrain = bool(drifted) or streak >= RETRAIN_DAYS
    print(f'  -> {verdict} (exit {code}) | retrain: {"YES, run python src/pipeline.py" if retrain else "no"} '
          f'| report: {html_path}')

    if code != EXIT_OK:
        psi_text = ', '.join(f'{col} PSI={drift[col][0]:.3f}' for col in DRIFT_COLUMNS)
        send_alert(f'{verdict} detected on {name}',
                   f'{psi_text} (limit {PSI_LIMIT})\n'
                   f'MAE={mae:.2f} days, limit {limit:.2f} (test MAE {test_mae:.2f} + {MAE_MARGIN:g}), '
                   f'{streak} consecutive days over the limit\n'
                   f'Retrain: {"yes -> python src/pipeline.py" if retrain else "not yet"}')
    if api_url:
        system_status(api_url)
    return code


class Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse exits 2 on bad arguments, but here 2 means Data Drift
        self.exit(1, f'{self.format_usage()}error: {message}\n')


if __name__ == '__main__':
    parser = Parser()
    parser.add_argument('--current', required=True, help='CSV of recent orders (same columns as the training CSV)')
    parser.add_argument('--api-url', default=os.environ.get('API_URL'), help='also check GET <url>/metrics')
    args = parser.parse_args()
    sys.exit(main(args.current, args.api_url))
