"""Feature engineering shared by training and inference."""

import numpy as np
import pandas as pd


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    lat1, lng1, lat2, lng2 = map(np.radians, [df.customer_lat, df.customer_lng, df.seller_lat, df.seller_lng])
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    df['distance_km'] = 2 * 6371 * np.arcsin(np.sqrt(a))
    df['same_state'] = (df.customer_state == df.seller_state).astype(int)
    ts = df.pop('order_purchase_timestamp')
    df['purchase_dow'] = ts.dt.dayofweek
    df['purchase_month'] = ts.dt.month
    df['purchase_hour'] = ts.dt.hour
    return df
