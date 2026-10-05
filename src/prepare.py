"""ข้อมูลดิบ Olist (raw_data + Data prepair/raw data/) -> shipping_distance_duration.csv ที่ train.py ใช้

ขั้นตอนเดียวกับที่ทีมทำมือใน notebook/สคริปต์ แต่รันต่อกันได้ด้วยคำสั่งเดียว:
  1. clean_orders     = clean_loma(for order).ipynb  (cell 18-26: orders/items/payments/reviews -> 1 แถวต่อ order ที่ส่งถึงแล้ว)
  2. clean_lookups    = eda_explore_for_cust_geo_prod_seller_clean.ipynb  (customers/geo/products/sellers)
  3. item_level       = order_items_full_merged.csv  (เดิมไม่มีสคริปต์ใน repo: join item + order + พิกัดลูกค้า/ผู้ขาย + น้ำหนัก)
  4. build_shipping_dataset ของ compute_shipping_distance.py  (import มาใช้ตรงๆ ไม่แก้ไฟล์เดิม)

  python src/prepare.py                       # เขียนทับ cleaned_data/feature extraction/shipping_distance_duration.csv
  python src/prepare.py --out /tmp/check.csv  # เขียนที่อื่นเพื่อเทียบกับไฟล์เดิม
"""
import argparse
import importlib.util
import os

import pandas as pd

RAW_DIR = 'raw_data + Data prepair/raw data'
SCRIPTS_DIR = 'raw_data + Data prepair'
OUT_PATH = 'cleaned_data/feature extraction/shipping_distance_duration.csv'

GEO_LAT_MIN, GEO_LAT_MAX = -34, 6
GEO_LNG_MIN, GEO_LNG_MAX = -74, -32
GEO_DIST_THRESHOLD_KM = 100


def _load_script(name):
    # โฟลเดอร์มีช่องว่างและ + จึง import แบบปกติไม่ได้
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS_DIR, f'{name}.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


distance = _load_script('compute_shipping_distance')
merge_all = _load_script('merge_all')


def read(name, **kwargs):
    return pd.read_csv(os.path.join(RAW_DIR, f'olist_{name}_dataset.csv'), **kwargs)


def clean_orders() -> pd.DataFrame:
    # notebook clean_loma: 1 แถวต่อ order ที่มีรีวิว + ส่งถึงแล้ว พร้อม delivery_days
    orders = read('orders', parse_dates=[
        'order_purchase_timestamp', 'order_approved_at', 'order_delivered_carrier_date',
        'order_delivered_customer_date', 'order_estimated_delivery_date'])
    items = read('order_items', parse_dates=['shipping_limit_date'])
    payments = read('order_payments')
    reviews = read('order_reviews', parse_dates=['review_creation_date', 'review_answer_timestamp'])
    customers = read('customers', usecols=['customer_id', 'customer_unique_id'])

    bad_carrier = ((orders['order_delivered_carrier_date'] < orders['order_purchase_timestamp'])
                   | (orders['order_delivered_customer_date'] < orders['order_delivered_carrier_date']))
    orders.loc[bad_carrier, 'order_delivered_carrier_date'] = pd.NaT

    items = items.merge(orders[['order_id', 'order_purchase_timestamp']], on='order_id', how='left')
    items.loc[(items['shipping_limit_date'] - items['order_purchase_timestamp']).dt.days > 60, 'shipping_limit_date'] = pd.NaT
    items_agg = items.drop(columns='order_purchase_timestamp').groupby('order_id', as_index=False).agg(
        n_items=('order_item_id', 'count'), n_products=('product_id', 'nunique'),
        n_sellers=('seller_id', 'nunique'), total_price=('price', 'sum'),
        total_freight=('freight_value', 'sum'), shipping_limit_date=('shipping_limit_date', 'max'))

    payments.loc[payments['payment_installments'] == 0, 'payment_installments'] = 1
    main_type = (payments.sort_values('payment_value', ascending=False).drop_duplicates('order_id')
                 [['order_id', 'payment_type']].rename(columns={'payment_type': 'main_payment_type'}))
    payments_agg = payments.groupby('order_id', as_index=False).agg(
        total_payment=('payment_value', 'sum'), n_payments=('payment_sequential', 'count'),
        max_installments=('payment_installments', 'max'),
        used_voucher=('payment_type', lambda s: int((s == 'voucher').any()))).merge(main_type, on='order_id', how='left')

    scores = reviews.groupby('order_id', as_index=False).agg(
        review_score=('review_score', 'mean'), n_reviews=('review_id', 'count'))
    df = (scores.merge(orders, on='order_id', how='left').merge(customers, on='customer_id', how='left')
          .merge(items_agg, on='order_id', how='left').merge(payments_agg, on='order_id', how='left'))
    df = df[df['order_status'] == 'delivered'].dropna(subset=['order_delivered_customer_date']).reset_index(drop=True)
    df['delivery_days'] = (df['order_delivered_customer_date'] - df['order_purchase_timestamp']).dt.days
    return df


def clean_geolocation(geo: pd.DataFrame) -> pd.DataFrame:
    # notebook eda_explore: ตัดพิกัดนอกบราซิล และพิกัดที่ห่างจาก median ของ zip ตัวเองเกิน 100 กม.
    geo = geo.copy()
    geo['geolocation_zip_code_prefix'] = geo['geolocation_zip_code_prefix'].astype(str).str.zfill(5)
    geo['geolocation_city'] = geo['geolocation_city'].str.strip()
    out_of_country = ((geo['geolocation_lat'] > GEO_LAT_MAX) | (geo['geolocation_lat'] < GEO_LAT_MIN)
                      | (geo['geolocation_lng'] > GEO_LNG_MAX) | (geo['geolocation_lng'] < GEO_LNG_MIN))
    zip_median = geo.groupby('geolocation_zip_code_prefix')[['geolocation_lat', 'geolocation_lng']].transform('median')
    far = distance.haversine_km(geo['geolocation_lat'], geo['geolocation_lng'],
                                zip_median['geolocation_lat'], zip_median['geolocation_lng']) > GEO_DIST_THRESHOLD_KM
    return geo[~(out_of_country | far)]


def clean_products(products: pd.DataFrame) -> pd.DataFrame:
    # notebook eda_explore: เติมน้ำหนัก/ขนาดที่หายด้วย median (ใช้แค่ product_weight_g ต่อ)
    products = products.copy()
    for col in ['product_weight_g', 'product_length_cm', 'product_height_cm', 'product_width_cm']:
        products[col] = products[col].fillna(products[col].median())
    return products


def item_level(orders: pd.DataFrame) -> pd.DataFrame:
    # แทน order_items_full_merged.csv: 1 แถวต่อ item ของ order ที่ผ่าน clean_orders
    zip_str = {'customer_zip_code_prefix': str, 'seller_zip_code_prefix': str}
    geo = merge_all.aggregate_geolocation(clean_geolocation(read('geolocation')))[
        ['geolocation_zip_code_prefix', 'geolocation_lat', 'geolocation_lng']]
    customers = read('customers', dtype=zip_str)[['customer_id', 'customer_zip_code_prefix', 'customer_city', 'customer_state']]
    sellers = read('sellers', dtype=zip_str)
    customers['customer_zip_code_prefix'] = customers['customer_zip_code_prefix'].str.zfill(5)
    sellers['seller_zip_code_prefix'] = sellers['seller_zip_code_prefix'].str.zfill(5)
    customers = customers.merge(geo.rename(columns={'geolocation_zip_code_prefix': 'customer_zip_code_prefix',
                                                    'geolocation_lat': 'customer_lat', 'geolocation_lng': 'customer_lng'}),
                                on='customer_zip_code_prefix', how='left')
    sellers = sellers.merge(geo.rename(columns={'geolocation_zip_code_prefix': 'seller_zip_code_prefix',
                                                'geolocation_lat': 'seller_lat', 'geolocation_lng': 'seller_lng'}),
                            on='seller_zip_code_prefix', how='left')
    order_cols = ['order_id', 'customer_id', 'order_purchase_timestamp', 'order_estimated_delivery_date',
                  'order_delivered_customer_date', 'delivery_days']
    return (read('order_items')[['order_id', 'order_item_id', 'product_id', 'seller_id', 'price', 'freight_value']]
            .merge(orders[order_cols], on='order_id', how='inner')
            .merge(customers, on='customer_id', how='left')
            .merge(clean_products(read('products'))[['product_id', 'product_weight_g']], on='product_id', how='left')
            .merge(sellers[['seller_id', 'seller_state', 'seller_lat', 'seller_lng']], on='seller_id', how='left'))


def prepare(out_path: str = OUT_PATH) -> pd.DataFrame:
    result = distance.build_shipping_dataset(item_level(clean_orders()))
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    result.to_csv(out_path, index=False)
    print(f'ข้อมูลดิบ -> {out_path}: {len(result):,} order, ไม่มีพิกัด {result["distance_km"].isnull().sum():,}')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=OUT_PATH)
    prepare(parser.parse_args().out)
