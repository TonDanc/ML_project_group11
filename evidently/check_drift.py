"""Test: do the two demo files drift away from the training data?

Run from repo root:  python evidently/check_drift.py

Reference = train split. Each file in FILES is compared against it column by column with Evidently.
Verdict uses PSI > 0.2 (KS p-value is printed for information only: with 66k reference rows it
flags even normal data). HTML reports go to evidently/reports/ (gitignored).
"""
import os
import sys

sys.path.insert(0, 'src')

import pandas as pd
from evidently import Report
from evidently.metrics import ValueDrift

from features import add_features
from schema import input_schema
from train import TARGET, load_splits

FILES = ['demo_data/drift_north.csv', 'demo_data/drift_blackfriday.csv']
# features from the drift criteria + the target (did real delivery time change?)
COLUMNS = ['total_weight_g', 'distance_km', 'total_price', 'total_freight', TARGET]
PSI_LIMIT = 0.2
OUT_DIR = 'evidently/reports'


def load_current(path: str) -> pd.DataFrame:
    """Same cleaning as load_splits: drop missing coordinates, validate, add distance_km."""
    raw = pd.read_csv(path).dropna(subset=['customer_lat', 'seller_lat'])
    X = input_schema.validate(raw)
    return add_features(X).assign(**{TARGET: raw[TARGET]})


def check(reference: pd.DataFrame, path: str) -> list[str]:
    """Print PSI and KS per column, save the HTML report, return the drifted columns."""
    current = load_current(path)
    name = os.path.splitext(os.path.basename(path))[0]

    metrics = []
    for col in COLUMNS:
        metrics += [ValueDrift(column=col, method='psi', threshold=PSI_LIMIT),
                    ValueDrift(column=col, method='ks', threshold=0.01)]
    snapshot = Report(metrics).run(current[COLUMNS], reference[COLUMNS])  # current first, reference second
    snapshot.save_html(f'{OUT_DIR}/{name}.html')

    values = [m['value'] for m in snapshot.dict()['metrics']]  # same order as metrics: psi, ks, psi, ks, ...
    drifted = []
    print(f'\n{name}  (rows={len(current)})')
    print(f'  {"column":<16} {"PSI":>7} {"KS p-value":>11}  result')
    for i, col in enumerate(COLUMNS):
        psi, ks_p = values[2 * i], values[2 * i + 1]
        is_drift = psi > PSI_LIMIT
        if is_drift:
            drifted.append(col)
        print(f'  {col:<16} {psi:>7.3f} {ks_p:>11.4f}  {"DRIFT" if is_drift else "ok"}')
    print('  ->', f'DRIFT in {", ".join(drifted)}' if drifted else 'no drift', f'| report: {OUT_DIR}/{name}.html')
    return drifted


if __name__ == '__main__':
    os.makedirs(OUT_DIR, exist_ok=True)
    train, _, _ = load_splits()
    reference = add_features(train)
    print(f'reference = train split, rows={len(reference)}')
    for path in FILES:
        check(reference, path)
