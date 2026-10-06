"""Build the demo CSVs used by monitor.py, pipeline.py and the live demo (see docs/data.md).

Run from repo root:  python demo_data/make_demo_data.py

Outputs (same columns as shipping_distance_duration.csv, including delivery_days):
  normal_orders.csv      500 random rows from the test split           -> no drift
  drift_north.csv        orders shipped to the North region            -> Data Drift (distance/weight shift)
  drift_blackfriday.csv  orders placed 2017-11-20..2017-11-27          -> Concept Drift (late deliveries)
  bad_orders.csv         50 normal rows with deliberately broken values -> Pandera rejects, pipeline stops

random_state=42 everywhere, so re-running gives identical files.
"""
import os
import sys

import numpy as np
import pandas as pd
import pandera.errors as pe

sys.path.insert(0, 'src')
from schema import input_schema  # noqa: E402

DATA_PATH = 'cleaned_data/feature extraction/shipping_distance_duration.csv'
OUT_DIR = 'demo_data'
SEED = 42
TARGET = 'delivery_days'

NORTH_STATES = ['AC', 'AP', 'AM', 'PA', 'RO', 'RR', 'TO']
BLACKFRIDAY = ('2017-11-20', '2017-11-27')  # Black Friday 2017 = Nov 24
N_NORMAL = 500
N_BAD = 50
MAX_BYTES = 2 * 1024 * 1024


def load():
    raw = pd.read_csv(DATA_PATH)
    # same filter as train.load_splits: rows without coordinates never reach the model
    return raw.dropna(subset=['customer_lat', 'seller_lat']).reset_index(drop=True)


def test_split(df):
    """Last 15% by purchase time, same cut as train.time_split."""
    ts = pd.to_datetime(df['order_purchase_timestamp'])
    df = df.assign(_ts=ts).sort_values('_ts').reset_index(drop=True).drop(columns='_ts')
    return df.iloc[int(len(df) * 0.85):]


def make_normal(df):
    return test_split(df).sample(n=N_NORMAL, random_state=SEED)


def make_north(df):
    return df[df['customer_state'].isin(NORTH_STATES)]


def make_blackfriday(df):
    ts = pd.to_datetime(df['order_purchase_timestamp'])
    start, end = pd.Timestamp(BLACKFRIDAY[0]), pd.Timestamp(BLACKFRIDAY[1]) + pd.Timedelta(days=1)
    return df[(ts >= start) & (ts < end)]


def make_bad(df):
    """50 normal rows, then break some of them on purpose (missing + corrupted values).

    Each kind of damage hits a different row so the demo can point at them one by one.
    Missing values are put in total_price / seller_state, not in lat: load_splits drops rows
    with missing lat *before* validation, so a missing lat would never reach Pandera.
    """
    bad = df.sample(n=N_BAD, random_state=SEED).reset_index(drop=True)
    bad = bad.astype({'total_weight_g': object, 'customer_state': object, 'customer_lat': object,
                      'n_items': object, 'total_price': object, 'seller_state': object,
                      'order_purchase_timestamp': object})
    rows = np.random.default_rng(SEED).choice(N_BAD, size=7, replace=False)
    damage = [
        ('total_weight_g', -500.0, 'negative weight'),
        ('customer_state', 'XX', 'unknown state'),
        ('customer_lat', 40.0, 'outside Brazil'),
        ('n_items', 'abc', 'wrong type'),
        ('order_purchase_timestamp', 'not-a-date', 'broken timestamp'),
        ('total_price', np.nan, 'missing value'),
        ('seller_state', np.nan, 'missing value'),
    ]
    for r, (col, val, why) in zip(rows, damage):
        print(f'  bad_orders row {r:2d}: {col} = {val!r}  ({why})')
        bad.at[r, col] = val
    return bad


def is_valid(df):
    try:
        input_schema.validate(df, lazy=True)
        return True
    except (pe.SchemaError, pe.SchemaErrors):
        return False


def save(df, name):
    path = os.path.join(OUT_DIR, name)
    df.to_csv(path, index=False)
    size = os.path.getsize(path)
    assert size < MAX_BYTES, f'{name} is {size / 1e6:.1f} MB, must be < 2 MB'
    print(f'{name:24s} {len(df):5d} rows  {size / 1024:6.0f} KB  '
          f'mean {TARGET} = {pd.to_numeric(df[TARGET], errors="coerce").mean():.1f}')


def main():
    df = load()
    print(f'source: {len(df)} rows, mean {TARGET} = {df[TARGET].mean():.1f}\n')

    normal = make_normal(df)
    north = make_north(df)
    blackfriday = make_blackfriday(df)
    bad = make_bad(df)
    print()

    save(normal, 'normal_orders.csv')
    save(north, 'drift_north.csv')
    save(blackfriday, 'drift_blackfriday.csv')
    save(bad, 'bad_orders.csv')

    for name, part in [('normal', normal), ('north', north), ('blackfriday', blackfriday)]:
        assert is_valid(part), f'{name} should pass input_schema'
    assert not is_valid(bad), 'bad_orders should be rejected by input_schema'
    print('\nok: normal/drift files pass the schema, bad_orders is rejected')


if __name__ == '__main__':
    main()
