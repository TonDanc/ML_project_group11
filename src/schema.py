"""Pandera schema for model input (one row = one order at checkout time).

Used by train.py before fitting and later by the API before predicting,
so both paths reject the same bad data.
"""
import pandera.pandas as pa

BR_STATES = ['AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA',
             'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO']

# Brazil bounding box, loose
LAT = pa.Check.in_range(-34, 6)
LNG = pa.Check.in_range(-74, -34)

input_schema = pa.DataFrameSchema(
    {
        'customer_state': pa.Column(str, pa.Check.isin(BR_STATES)),
        'seller_state': pa.Column(str, pa.Check.isin(BR_STATES)),
        'customer_lat': pa.Column(float, LAT),
        'customer_lng': pa.Column(float, LNG),
        'seller_lat': pa.Column(float, LAT),
        'seller_lng': pa.Column(float, LNG),
        'n_sellers': pa.Column(int, pa.Check.in_range(1, 20)),
        'n_items': pa.Column(int, pa.Check.in_range(1, 100)),
        'total_price': pa.Column(float, pa.Check.gt(0)),
        'total_freight': pa.Column(float, pa.Check.ge(0)),
        'total_weight_g': pa.Column(float, pa.Check.in_range(0, 500_000)),
        'estimated_delivery_days': pa.Column(int, pa.Check.in_range(0, 200)),
        'order_purchase_timestamp': pa.Column('datetime64[ns]'),
    },
    coerce=True,   # "12" -> 12, str timestamp -> datetime; uncoercible values fail
    strict='filter',  # drop extra columns (ids, target) instead of failing
)
