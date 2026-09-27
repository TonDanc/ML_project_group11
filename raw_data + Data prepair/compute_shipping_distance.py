"""
คำนวณระยะทาง (seller -> customer, กม.) และระยะเวลาจัดส่ง (วัน) ต่อ order
เพื่อใช้เป็น dataset สำหรับระบบพยากรณ์ระยะเวลาจัดส่งสินค้า (delivery time prediction)

ใช้ข้อมูลจาก archive/clean/order_items_full_merged.csv เท่านั้น (ตามที่กำหนด)

ปัญหาข้อมูลที่พบและวิธีจัดการ (ดูรายละเอียดในโค้ดแต่ละจุด):
    1. Customer/seller บางรายไม่มีพิกัด (zip ไม่ตรงกับ geolocation เลย)
       -> distance_km จะเป็น NaN สำหรับ order นั้น ไม่ impute เอง
    2. Order ที่มีหลาย seller (1,261 จาก 95,824 = 1.3%) -> ใช้ seller ที่ไกลสุดเป็นตัวแทน
       ทั้ง distance_km, seller_lat, seller_lng, seller_state ของ order นั้น
       (สมมติฐาน: จัดส่งช้าตาม seller ไกลสุด — เลือกให้ lat/lng ตรงกับระยะทางเสมอ)
    3. Data leakage: "late_days", "is_late", "review_score", "n_reviews" คำนวณมาจาก/
       หลังวันที่ได้รับสินค้าจริง -> ไม่ใส่เป็น feature ในไฟล์ผลลัพธ์

รันจาก working directory ที่มีโฟลเดอร์ archive/ อยู่ (เช่น data/):
    python compute_shipping_distance.py
"""
import os
import numpy as np
import pandas as pd

CLEAN_DIR = 'archive/clean'
IN_PATH = f'{CLEAN_DIR}/order_items_full_merged.csv'
OUT_PATH = f'{CLEAN_DIR}/shipping_distance_duration.csv'


def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371
    lat1, lng1, lat2, lng2 = map(np.radians, [lat1, lng1, lat2, lng2])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlng / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def load_data() -> pd.DataFrame:
    df = pd.read_csv(
        IN_PATH,
        parse_dates=['order_purchase_timestamp', 'order_estimated_delivery_date',
                     'order_delivered_customer_date'],
    )
    return df


def report_data_gaps(df: pd.DataFrame) -> None:
    """แจ้งปัญหาการเชื่อมโยงข้อมูลที่พบ ไม่เงียบผ่าน"""
    n_orders = df['order_id'].nunique()

    missing_customer_geo = df.loc[df['customer_lat'].isnull(), 'order_id'].nunique()
    missing_seller_geo = df.loc[df['seller_lat'].isnull(), 'order_id'].nunique()
    print(f"[data gap] orders ที่ customer ไม่มีพิกัด (zip ไม่ตรงกับ geolocation): {missing_customer_geo:,} / {n_orders:,}")
    print(f"[data gap] orders ที่ seller ไม่มีพิกัด (zip ไม่ตรงกับ geolocation):   {missing_seller_geo:,} / {n_orders:,}")

    n_sellers_per_order = df.groupby('order_id')['seller_id'].nunique()
    multi_seller_orders = int((n_sellers_per_order > 1).sum())
    print(f"[data gap] orders ที่มีมากกว่า 1 seller: {multi_seller_orders:,} / {n_orders:,} "
          f"-> ใช้ระยะทางไกลสุด (max) ของ seller ในกลุ่มนั้นแทน")


def build_shipping_dataset(df: pd.DataFrame) -> pd.DataFrame:
    # ระยะทางคำนวณที่ระดับ item ก่อน (ต่างกันได้ถ้า order มีหลาย seller คนละพิกัด)
    df = df.copy()
    df['item_distance_km'] = haversine_km(
        df['customer_lat'], df['customer_lng'], df['seller_lat'], df['seller_lng']
    )

    # เลือกแถว (seller) ที่ไกลสุดต่อ order เป็น "ตัวแทน" ของ order นั้น แล้วดึง
    # lat/lng/state ของ seller คนนั้นมาด้วย เพื่อให้ lat/lng สอดคล้องกับ distance_km เสมอ
    # (ถ้าใช้ mode/first แยกกันจะได้ seller คนละคนกับที่ใช้คำนวณระยะทาง สับสนตอนโมเดลใช้ร่วมกัน)
    # ถ้า order ไม่มีพิกัดเลยสักแถว (item_distance_km เป็น NaN ทุกแถว) จะได้แถวแรกของ order แทน
    df_sorted = df.sort_values('item_distance_km', ascending=False, na_position='last')
    representative = df_sorted.drop_duplicates(subset='order_id', keep='first')[
        ['order_id', 'customer_id', 'customer_state', 'customer_city',
         'customer_lat', 'customer_lng',
         'seller_state', 'seller_lat', 'seller_lng',
         'item_distance_km']
    ].rename(columns={'item_distance_km': 'distance_km'})

    other_aggs = df.groupby('order_id', as_index=False).agg(
        n_sellers=('seller_id', 'nunique'),
        n_items=('order_item_id', 'count'),
        total_price=('price', 'sum'),
        total_freight=('freight_value', 'sum'),
        total_weight_g=('product_weight_g', 'sum'),
        order_purchase_timestamp=('order_purchase_timestamp', 'first'),
        order_estimated_delivery_date=('order_estimated_delivery_date', 'first'),
        order_delivered_customer_date=('order_delivered_customer_date', 'first'),
        delivery_days=('delivery_days', 'first'),  # target
    )

    order_level = representative.merge(other_aggs, on='order_id', how='left')

    order_level['same_state'] = (order_level['customer_state'] == order_level['seller_state']).astype(int)
    order_level['estimated_delivery_days'] = (
        order_level['order_estimated_delivery_date'] - order_level['order_purchase_timestamp']
    ).dt.days

    return order_level


if __name__ == '__main__':
    df = load_data()
    print(f"โหลด {IN_PATH}: {df.shape[0]:,} แถว (item-level)")
    print()

    report_data_gaps(df)
    print()

    result = build_shipping_dataset(df)

    print(f"FINAL (order-level): {result.shape[0]:,} แถว x {result.shape[1]} คอลัมน์")
    print(f"distance_km ที่เป็น NaN (customer/seller ไม่มีพิกัด): {result['distance_km'].isnull().sum():,}")
    print()
    print(result[['customer_lat', 'customer_lng', 'seller_lat', 'seller_lng',
                   'distance_km', 'delivery_days', 'estimated_delivery_days',
                   'same_state', 'n_sellers']].describe())

    os.makedirs(CLEAN_DIR, exist_ok=True)
    result.to_csv(OUT_PATH, index=False)
    print()
    print("บันทึกไฟล์แล้วที่:", os.path.abspath(OUT_PATH))
    print()
    print("หมายเหตุ: ไม่ได้ใส่ late_days / is_late / review_score / n_reviews เป็น feature")
    print("เพราะคำนวณมาจาก/หลังวันที่ได้รับสินค้าจริง จะเป็น data leakage กับ target (delivery_days)")
