"""Model registry commands: promotion gate, rollback, status.

  python src/registry.py promote          # gate @challenger -> @champion, exit 1 if rejected
  python src/registry.py rollback [VER]   # @champion -> previous passed version (or VER)
  python src/registry.py status           # list versions, aliases, gate result

Status lives in MLflow aliases (@champion = serving, @challenger = newest candidate)
and version tags (gate=passed/failed, gate_reason, rolled_back).
"""
import sys
import time

import mlflow
import numpy as np
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from sklearn.metrics import mean_absolute_error

from train import MODEL_NAME, TRACKING_URI, load_splits, xy

MIN_IMPROVEMENT = 0.05  # gating metric: new MAE must be >= 5% lower than the champion's
MAX_P95_MS = 200        # gating metric: single-order latency


def alias_version(client, alias):
    try:
        return client.get_model_version_by_alias(MODEL_NAME, alias).version
    except MlflowException:
        return None


def p95_latency_ms(model, X, n=200):
    rows = [X.iloc[[i % len(X)]] for i in range(n)]
    times = []
    for row in rows:
        t = time.perf_counter()
        model.predict(row)
        times.append((time.perf_counter() - t) * 1000)
    return float(np.percentile(times, 95))


def promote(client):
    new_v = alias_version(client, 'challenger')
    if new_v is None:
        sys.exit('no @challenger, run src/train.py first')
    old_v = alias_version(client, 'champion')
    if new_v == old_v:
        sys.exit(f'v{new_v} is already @champion')

    # score champion and challenger on the SAME current test split (fair even if they were trained on different data)
    train, _, test = load_splits()
    X, y = xy(test)
    new = mlflow.sklearn.load_model(f'models:/{MODEL_NAME}/{new_v}')
    new_mae = mean_absolute_error(y, new.predict(X))
    dummy_mae = mean_absolute_error(y, np.full(len(y), xy(train)[1].median()))
    p95 = p95_latency_ms(new, X)
    print(f'challenger v{new_v}: test MAE={new_mae:.3f}  p95={p95:.1f} ms  (dummy MAE={dummy_mae:.3f})')

    fails = []
    if new_mae >= dummy_mae:
        fails.append(f'MAE {new_mae:.3f} does not beat dummy {dummy_mae:.3f}')
    if p95 >= MAX_P95_MS:
        fails.append(f'p95 {p95:.1f} ms >= {MAX_P95_MS} ms')
    if old_v is not None:
        old_mae = mean_absolute_error(y, mlflow.sklearn.load_model(f'models:/{MODEL_NAME}/{old_v}').predict(X))
        print(f'champion   v{old_v}: test MAE={old_mae:.3f}  (need <= {old_mae * (1 - MIN_IMPROVEMENT):.3f})')
        if new_mae > old_mae * (1 - MIN_IMPROVEMENT):
            fails.append(f'MAE {new_mae:.3f} not {MIN_IMPROVEMENT:.0%} better than champion v{old_v} ({old_mae:.3f})')

    for k, v in {'test_mae': f'{new_mae:.4f}', 'p95_ms': f'{p95:.1f}'}.items():
        client.set_model_version_tag(MODEL_NAME, new_v, k, v)
    if fails:
        client.set_model_version_tag(MODEL_NAME, new_v, 'gate', 'failed')
        client.set_model_version_tag(MODEL_NAME, new_v, 'gate_reason', '; '.join(fails))
        sys.exit('REJECTED: ' + '; '.join(fails))
    client.set_model_version_tag(MODEL_NAME, new_v, 'gate', 'passed')
    client.set_registered_model_alias(MODEL_NAME, 'champion', new_v)
    print(f'PROMOTED v{new_v} to @champion (was v{old_v})')


def rollback(client, target=None):
    cur = alias_version(client, 'champion')
    if cur is None:
        sys.exit('no @champion to roll back')
    if target is None:
        passed = [int(v.version) for v in client.search_model_versions(f"name='{MODEL_NAME}'")
                  if v.tags.get('gate') == 'passed' and int(v.version) < int(cur)]
        if not passed:
            sys.exit(f'no earlier passed version than v{cur}')
        target = max(passed)
    client.set_model_version_tag(MODEL_NAME, cur, 'rolled_back', 'true')
    client.set_registered_model_alias(MODEL_NAME, 'champion', str(target))
    print(f'ROLLED BACK @champion v{cur} -> v{target}. Restart the API to load it.')


def status(client):
    try:
        alias_of = client.get_registered_model(MODEL_NAME).aliases  # {alias: version}; search results don't carry aliases
    except MlflowException:
        sys.exit(f'no model {MODEL_NAME!r} registered yet, run src/train.py first')
    for v in sorted(client.search_model_versions(f"name='{MODEL_NAME}'"), key=lambda v: int(v.version)):
        aliases = ','.join('@' + a for a, ver in alias_of.items() if ver == v.version) or '-'
        tags = {k: v.tags[k] for k in ('gate', 'test_mae', 'p95_ms', 'rolled_back', 'gate_reason') if k in v.tags}
        print(f'v{v.version:<3} {aliases:<24} run={v.run_id}  {tags}')


if __name__ == '__main__':
    mlflow.set_tracking_uri(TRACKING_URI)
    client = MlflowClient()
    cmd, *args = sys.argv[1:] or ['status']
    if cmd == 'promote':
        promote(client)
    elif cmd == 'rollback':
        rollback(client, *args)
    elif cmd == 'status':
        status(client)
    else:
        sys.exit(__doc__)
