"""
Merge ไฟล์ใน archive/clean/ เข้าด้วยกัน โดยใช้ customers เป็นตารางหลัก

ไฟล์ที่ merge ได้จริง (มีคีย์เชื่อมกัน):
    - olist_customers_dataset_clean.csv   (ฐาน, 1 แถว/customer)
    - order_clean_merged - order_clean_merged.csv  (1 แถว/order, join บน customer_id)
    - olist_geolocation_dataset_clean.csv (aggregate เหลือ 1 แถว/zip ก่อน join บน zip_code_prefix)

ไฟล์ที่ "ไม่" merge เข้ามา (ไม่มีคีย์เชื่อมกับ customer ได้จริง):
    - olist_products_dataset_clean.csv  ไม่มี product_id อยู่ใน order_clean_merged
      (มีแค่ n_products ซึ่งเป็นตัวนับ ไม่ใช่คีย์)
    - olist_sellers_dataset_clean.csv   เหตุผลเดียวกัน ไม่มี seller_id ให้เชื่อม

รันจาก working directory ที่มีโฟลเดอร์ archive/ อยู่ (เช่น data/):
    python merge_all.py
"""
import os
import pandas as pd

CLEAN_DIR = 'archive/clean'
OUT_DIR = 'archive/clean'


def load_data():
    customers = pd.read_csv(f'{CLEAN_DIR}/olist_customers_dataset_clean.csv',
                             dtype={'customer_zip_code_prefix': str})
    orders = pd.read_csv(f'{CLEAN_DIR}/order_clean_merged - order_clean_merged.csv')
    geo = pd.read_csv(f'{CLEAN_DIR}/olist_geolocation_dataset_clean.csv',
                       dtype={'geolocation_zip_code_prefix': str})
    return customers, orders, geo


def aggregate_geolocation(geo: pd.DataFrame) -> pd.DataFrame:
    """ยุบ geolocation เหลือ 1 แถวต่อ zip_code_prefix ก่อน merge

    เหตุผล: 1 zip มีพิกัดได้หลายร้อยจุด (many-to-many กับ customers/sellers)
    ถ้า join ตรงๆ จะทำให้แถวระเบิด (ทดสอบแล้วได้ถึง 18 ล้านแถวตอนลองกับ orders)
    ใช้ median แทน mean เพราะทนต่อ outlier ในกลุ่มเดียวกันมากกว่า
    """
    return (
        geo.groupby('geolocation_zip_code_prefix')
        .agg(
            geolocation_lat=('geolocation_lat', 'median'),
            geolocation_lng=('geolocation_lng', 'median'),
            geolocation_city=('geolocation_city', lambda s: s.mode().iloc[0]),
            geolocation_state=('geolocation_state', lambda s: s.mode().iloc[0]),
        )
        .reset_index()
    )


def build_merged_dataset() -> pd.DataFrame:
    customers, orders, geo = load_data()

    n_customers = len(customers)
    n_orders = len(orders)

    geo_agg = aggregate_geolocation(geo)
    assert geo_agg['geolocation_zip_code_prefix'].is_unique, "geolocation aggregate ต้องเหลือ 1 แถวต่อ zip"

    # customers เป็นหลัก -> left join orders (1-to-1 บน customer_id) -> left join geo (many-to-1 บน zip)
    final = (
        customers
        .merge(orders, on='customer_id', how='left', suffixes=('', '_order'))
        .merge(geo_agg, left_on='customer_zip_code_prefix',
               right_on='geolocation_zip_code_prefix', how='left', suffixes=('', '_geo'))
    )

    print(f"customers (base):        {n_customers:,} แถว")
    print(f"orders (order-level):     {n_orders:,} แถว")
    print(f"geolocation aggregated:   {len(geo_agg):,} แถว (1 ต่อ zip, จากเดิม {len(geo):,} แถว)")
    print(f"FINAL merged:             {len(final):,} แถว")
    print(f"FINAL columns:            {len(final.columns)}")
    print(f"unique customer_id ใน final: {final['customer_id'].nunique():,} (ต้องเท่ากับ {n_customers:,})")
    print(f"customers ที่ไม่มี order จับคู่: {final['order_id'].isnull().sum():,} แถว")
    print(f"customers ที่ไม่มี geolocation จับคู่ (zip ไม่ตรงกับ geo เลย): {final['geolocation_lat'].isnull().sum():,} แถว")

    assert len(final) == n_customers, "แถวเพิ่ม/ลดจากฐาน customers — เช็ค fan-out"
    assert final['customer_id'].nunique() == n_customers, "ลูกค้าหายไปจาก final table"

    return final


if __name__ == '__main__':
    merged = build_merged_dataset()

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = f'{OUT_DIR}/merged_customers_orders_geo.csv'
    merged.to_csv(out_path, index=False)
    print()
    print("บันทึกไฟล์ merge แล้วที่:", os.path.abspath(out_path))
    print()
    print("หมายเหตุ: olist_products_dataset_clean.csv และ olist_sellers_dataset_clean.csv")
    print("ไม่ได้ merge เข้ามา เพราะไม่มีคีย์ (product_id / seller_id) เชื่อมกับ customer ได้")
    print("ยังคงเป็นไฟล์แยกตามเดิมใน archive/clean/")
