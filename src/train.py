"""Train candidate models, log every run to MLflow, register the best one as @challenger.

Run from repo root:  python src/train.py
Then:                python src/registry.py promote   (gate -> @champion)

Each run logs the 6 things the course asks for: code version (git commit), data version
(md5 of the CSV), hyperparameters, metrics, output files (the model), environment
(python/platform + pip requirements saved with the model).
The model is a full sklearn Pipeline (feature engineering + model), so serving loads one
object and applies exactly the same transforms.
"""
import hashlib
import os
import platform
import subprocess

import mlflow
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder

from schema import input_schema
from features import add_features

DATA_PATH = 'cleaned_data/feature extraction/shipping_distance_duration.csv'
TARGET = 'delivery_days'
CAT_COLS = ['customer_state', 'seller_state']
EXPERIMENT = 'delivery_eta'
MODEL_NAME = 'delivery_eta'
# MLflow saves sklearn models with skops, which refuses types it can't vet. We only load models
# we trained ourselves, so trust exactly these two: our feature function and HGB's tree nodes.
TRUSTED_TYPES = ['features.add_features', 'sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor']
# no server configured -> local sqlite file (the registry needs a database backend)
TRACKING_URI = os.environ.get('MLFLOW_TRACKING_URI', 'sqlite:///mlflow.db')


def make_pipeline(model) -> Pipeline:
    encode = ColumnTransformer(
        [('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), CAT_COLS)],
        remainder='passthrough',
    )
    return Pipeline([('features', FunctionTransformer(add_features)), ('encode', encode), ('model', model)])


def time_split(df: pd.DataFrame):
    """70/15/15 by purchase time: train on the past, test on the future."""
    df = df.sort_values('order_purchase_timestamp').reset_index(drop=True)
    i, j = int(len(df) * 0.70), int(len(df) * 0.85)
    return df.iloc[:i], df.iloc[i:j], df.iloc[j:]


def load_splits(path=DATA_PATH):
    raw = pd.read_csv(path)
    # 0.5% of orders have a zip code not found in geolocation -> no coordinates. Drop, don't impute:
    # at serving time the same payload would be rejected by the schema anyway.
    n = len(raw)
    raw = raw.dropna(subset=['customer_lat', 'seller_lat'])
    print(f'dropped {n - len(raw)} rows with missing coordinates')
    y_all = raw[TARGET]
    X_all = input_schema.validate(raw)  # raises SchemaError -> script stops before training
    return time_split(X_all.assign(**{TARGET: y_all}))


def xy(part):
    return part.drop(columns=TARGET), part[TARGET]


def md5(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def git_commit():
    # inside Docker there is no .git -> pass GIT_COMMIT from outside
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return os.environ.get('GIT_COMMIT', 'unknown')


MODELS = {
    'dummy_median': DummyRegressor(strategy='median'),  # floor: a model must beat "always guess the median"
    'linear_regression': LinearRegression(),
    # absolute_error = optimize MAE directly (target is right-skewed, max 208 days)
    'hgb_default': HistGradientBoostingRegressor(loss='absolute_error', random_state=42),
    'hgb_bigger': HistGradientBoostingRegressor(loss='absolute_error', max_iter=300, learning_rate=0.05,
                                                max_leaf_nodes=63, random_state=42),
}

if __name__ == '__main__':
    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT)

    train, val, test = load_splits()
    print(f'train={len(train)} val={len(val)} test={len(test)}')
    X_tr, y_tr = xy(train)
    common_tags = {'git_commit': git_commit(), 'python': platform.python_version(), 'platform': platform.platform()}
    common_params = {'data_path': DATA_PATH, 'data_md5': md5(DATA_PATH), 'data_rows': len(train) + len(val) + len(test),
                     'n_train': len(train), 'n_val': len(val), 'n_test': len(test), 'split': 'time 70/15/15'}

    # "current model" = Olist's own estimate shown to customers today (reference only, not a candidate)
    for name, part in [('val', val), ('test', test)]:
        print(f'[{name}] olist estimate MAE={mean_absolute_error(part[TARGET], part["estimated_delivery_days"]):.3f}')

    # e.g. CANDIDATES=dummy_median,linear_regression -> train only these (used to build an "old" version for the rollback demo)
    only = os.environ.get('CANDIDATES')
    candidates = {k: v for k, v in MODELS.items() if not only or k in only.split(',')}

    results = []
    for name, model in candidates.items():
        with mlflow.start_run(run_name=name, tags=common_tags) as run:
            pipe = make_pipeline(model).fit(X_tr, y_tr)
            mlflow.log_params({**common_params, 'model': name, **model.get_params()})
            metrics = {}
            for split, part in [('val', val), ('test', test)]:
                X, y = xy(part)
                pred = pipe.predict(X)
                metrics[f'{split}_mae'] = mean_absolute_error(y, pred)
                metrics[f'{split}_rmse'] = root_mean_squared_error(y, pred)
            mlflow.log_metrics(metrics)
            info = mlflow.sklearn.log_model(pipe, name='model', input_example=X_tr.head(3),
                                            code_paths=['src/features.py'],
                                            skops_trusted_types=TRUSTED_TYPES)
            results.append((metrics['val_mae'], name, info.model_uri))
            print(f'{name:<20} val MAE={metrics["val_mae"]:.3f}  test MAE={metrics["test_mae"]:.3f}  run={run.info.run_id}')

    # pick by val, never by test (test is for the promotion gate)
    val_mae, best, uri = min(results)
    version = mlflow.register_model(uri, MODEL_NAME).version
    mlflow.MlflowClient().set_registered_model_alias(MODEL_NAME, 'challenger', version)
    print(f'registered {MODEL_NAME} v{version} ({best}, val MAE={val_mae:.3f}) as @challenger')
