"""Run: python src/test_schema.py"""
import pandas as pd
import pandera.errors as pe

from schema import input_schema

GOOD = dict(customer_state='SP', seller_state='SP', customer_lat=-23.5, customer_lng=-46.6,
            seller_lat=-23.6, seller_lng=-46.7, n_sellers=1, n_items=2, total_price=100.0,
            total_freight=15.0, total_weight_g=800.0, estimated_delivery_days=10,
            order_purchase_timestamp='2018-05-01 10:00:00')


def rejects(**change):
    row = {**GOOD, **change}
    row = {k: v for k, v in row.items() if v is not ...}  # ... = drop the column
    try:
        input_schema.validate(pd.DataFrame([row]))
        return False
    except (pe.SchemaError, pe.SchemaErrors):  # coercion failures raise the plural one
        return True


if __name__ == '__main__':
    assert input_schema.validate(pd.DataFrame([GOOD])).shape == (1, 13)
    assert rejects(customer_lat=...)          # missing column
    assert rejects(customer_lat=None)         # null
    assert rejects(customer_state='XX')       # unknown state
    assert rejects(total_weight_g=-5.0)       # negative weight
    assert rejects(customer_lat=40.0)         # outside Brazil
    assert rejects(n_items='abc')             # wrong type
    print('schema checks ok')
