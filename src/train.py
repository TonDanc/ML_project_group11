"""Baseline model: predict delivery_days from order features.

Run from repo root:  python src/train.py
Output: models/model.joblib (full sklearn Pipeline: feature engineering + model),
so serving loads one object and applies exactly the same transforms.
"""
import os

import joblib
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
MODEL_PATH = 'models/model.joblib'
TARGET = 'delivery_days'
CAT_COLS = ['customer_state', 'seller_state']


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


def report(name, y, pred):
    print(f'{name:<28} MAE={mean_absolute_error(y, pred):6.3f}  RMSE={root_mean_squared_error(y, pred):6.3f}')


if __name__ == '__main__':
    raw = pd.read_csv(DATA_PATH)

    # 0.5% of orders have a zip code not found in geolocation -> no coordinates. Drop, don't impute:
    # at serving time the same payload would be rejected by the schema anyway.
    n = len(raw)
    raw = raw.dropna(subset=['customer_lat', 'seller_lat'])
    print(f'dropped {n - len(raw)} rows with missing coordinates')

    y_all = raw[TARGET]
    X_all = input_schema.validate(raw)  # raises SchemaError -> script stops before training
    train, val, test = time_split(X_all.assign(**{TARGET: y_all}))
    print(f'train={len(train)} val={len(val)} test={len(test)}')

    X_tr, y_tr = train.drop(columns=TARGET), train[TARGET]

    # "current model" = Olist's own estimate shown to customers today
    for name, part in [('val', val), ('test', test)]:
        report(f'[{name}] olist estimate', part[TARGET], part['estimated_delivery_days'])

    models = {
        'dummy_median': DummyRegressor(strategy='median'),  # floor: a model must beat "always guess the median"
        'linear_regression': LinearRegression(),
        # default hyperparams; absolute_error = optimize MAE directly (target is right-skewed, max 208 days)
        'hist_gradient_boosting': HistGradientBoostingRegressor(loss='absolute_error', random_state=42),
    }
    for name, model in models.items():
        pipe = make_pipeline(model).fit(X_tr, y_tr)
        for split, part in [('val', val), ('test', test)]:
            report(f'[{split}] {name}', part[TARGET], pipe.predict(part.drop(columns=TARGET)))

    os.makedirs('models', exist_ok=True)
    joblib.dump(pipe, MODEL_PATH)  # last one = hist_gradient_boosting
    print('saved', MODEL_PATH)
