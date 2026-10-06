# ข้อมูล: ที่มา การเตรียม การตรวจสอบ และข้อมูล demo

## ภาพรวม

```
raw_data + Data prepair/raw data/   ข้อมูลดิบ Olist (Kaggle, CC BY-NC-SA 4.0)
        │  python src/prepare.py
        ▼
cleaned_data/feature extraction/shipping_distance_duration.csv   1 แถว = 1 order ที่ส่งถึงแล้ว
        │  load_splits(): ตัดแถวไม่มีพิกัด → ตรวจ schema (Pandera) → แบ่งตามเวลา
        ▼
train 70% / val 15% / test 15%
```

## เตรียมข้อมูล: `src/prepare.py`

แปลงข้อมูลดิบ 8 ไฟล์ (`olist_customers`, `geolocation`, `order_items`, `order_payments`, `order_reviews`, `orders`, `products`, `sellers`) เป็น CSV ที่ใช้เทรน รวม logic ที่เดิมทีมทำมือใน notebook ให้รันต่อกันได้ด้วยคำสั่งเดียว

| ขั้น | ทำอะไร | ที่มาของ logic |
|---|---|---|
| `clean_orders()` | orders/items/payments/reviews → 1 แถวต่อ order ที่มีรีวิวและส่งถึงแล้ว + `delivery_days` | `clean_loma(for order).ipynb` cell 18–26 |
| `clean_geolocation()`, `clean_products()` | ตัดพิกัดนอกบราซิลหรือห่าง median ของ zip เกิน 100 กม., เติมน้ำหนักสินค้าที่หายด้วย median | `eda_explore_for_cust_geo_prod_seller_clean.ipynb` |
| `item_level()` | join item + order + พิกัดลูกค้า/ผู้ขาย + น้ำหนัก | `aggregate_geolocation()` ของ `merge_all.py` |
| `build_shipping_dataset()` | รวมเป็นระดับ order และคำนวณระยะทาง | import จาก `compute_shipping_distance.py` ตรงๆ |

```bash
python src/prepare.py                       # เขียนทับ cleaned_data/feature extraction/shipping_distance_duration.csv (~40 วินาที)
python src/prepare.py --out /tmp/check.csv  # เขียนที่อื่นเพื่อเทียบ
```

ผลลัพธ์: 95,824 order × 21 คอลัมน์ รันซ้ำได้ไฟล์เหมือนเดิมทุก byte (ตรวจจาก clone ใหม่แล้ว `git status` ว่าง) `pipeline.py` เรียกขั้นนี้เป็น task แรก ถ้าไม่มีโฟลเดอร์ข้อมูลดิบ (เช่นใน Docker image) จะข้ามแล้วใช้ CSV ที่ commit ไว้

## คอลัมน์ของ `shipping_distance_duration.csv`

| คอลัมน์ | ความหมาย | ใช้เป็น feature |
|---|---|---|
| `order_id`, `customer_id` | รหัส | ไม่ใช่ (identifier) |
| `customer_state`, `seller_state` | รัฐของลูกค้าและผู้ขาย เช่น SP, RJ | ✅ |
| `customer_city` | เมืองของลูกค้า (~4,000 ค่า) | ไม่ได้ใช้ (cardinality สูง) |
| `customer_lat/lng`, `seller_lat/lng` | พิกัด (median ของ zip code จาก geolocation) | ✅ |
| `distance_km` | ระยะทางเส้นตรง (haversine) ผู้ขาย → ลูกค้า | ✅ (โมเดลคำนวณใหม่เองจากพิกัดใน `features.add_features`) |
| `n_sellers`, `n_items` | จำนวนผู้ขายและจำนวนชิ้นใน order | ✅ |
| `total_price`, `total_freight`, `total_weight_g` | ราคารวม ค่าส่งรวม น้ำหนักรวม (กรัม) | ✅ |
| `order_purchase_timestamp` | เวลาสั่งซื้อ | ✅ ผ่านฟีเจอร์ day-of-week, เดือน, ชั่วโมง |
| `order_estimated_delivery_date` | วันที่ Olist ประเมินไว้ตอนสั่ง | ใช้ในรูป `estimated_delivery_days` แทน |
| `estimated_delivery_days` | วันที่ประเมิน − วันสั่ง | ✅ (รู้ตั้งแต่ตอนซื้อ) |
| `same_state` | 1 ถ้ารัฐเดียวกัน | ✅ |
| `order_delivered_customer_date` | วันที่ลูกค้าได้รับจริง | ❌ **ห้ามใช้** ใช้คำนวณ target |
| `delivery_days` | วันได้รับจริง − วันสั่ง | 🎯 **target** |

**Data leakage:** ห้ามใช้ `order_delivered_customer_date` และค่าใดๆ ที่รู้หลังส่งถึง (`late_days`, `is_late`, `review_score`) เป็น feature schema ใช้ `strict='filter'` จึงตัดคอลัมน์เหล่านี้ทิ้งอัตโนมัติก่อนเข้าโมเดล

## ค่าที่หายไปและค่าผิดปกติ

| ปัญหา | จัดการอย่างไร | เหตุผล |
|---|---|---|
| 503 order ไม่มีพิกัด (zip ไม่อยู่ในตาราง geolocation: 291 ฝั่งลูกค้า, 217 ฝั่งผู้ขาย) | `load_splits()` **ตัดทิ้ง** ไม่ impute | ตอนใช้งานจริง payload ที่ไม่มีพิกัดก็ไม่ผ่าน schema อยู่แล้ว |
| พิกัด geolocation นอกบราซิล หรือห่าง median ของ zip > 100 กม. | `prepare.py` ตัดก่อนหาค่า median | กันพิกัดผิดดึงตำแหน่งเพี้ยน |
| น้ำหนักสินค้าหาย | `prepare.py` เติมด้วย median | ตามที่ทำไว้ใน notebook ทำความสะอาด |
| 1,261 order (1.3%) มีหลายผู้ขาย | ใช้ผู้ขายที่ไกลที่สุดเป็นตัวแทน | สมมติว่าการส่งช้าตามผู้ขายที่ไกลสุด |
| ค่านอกช่วงที่เป็นไปได้ | schema ปฏิเสธ (ตารางด้านล่าง) | |

ข้อจำกัด: `distance_km` เป็นระยะเส้นตรง ไม่ใช่ระยะถนน dataset ไม่มีข้อมูลเส้นทางหรือบริษัทขนส่ง

## Schema: `src/schema.py` (Pandera)

`input_schema` ตรวจข้อมูลทีละ order ใช้ตัวเดียวกันทั้งตอนเทรน (`load_splits`) และตอนให้บริการ (`/predict`)

| คอลัมน์ | กฎ |
|---|---|
| `customer_state`, `seller_state` | รหัสรัฐบราซิล 27 รัฐ |
| `customer_lat/lng`, `seller_lat/lng` | อยู่ในกรอบบราซิล (lat −34..6, lng −74..−34) |
| `n_sellers` | 1–20 |
| `n_items` | 1–100 |
| `total_price` | > 0 |
| `total_freight` | ≥ 0 |
| `total_weight_g` | 0–500,000 |
| `estimated_delivery_days` | 0–200 |
| `order_purchase_timestamp` | แปลงเป็นวันเวลาได้ |

- ทุกคอลัมน์ห้ามว่าง และห้ามขาดคอลัมน์
- `coerce=True` แปลงชนิดให้เอง เช่น `"12"` → `12` ถ้าแปลงไม่ได้ถือว่าไม่ผ่าน
- `strict='filter'` ตัดคอลัมน์เกินทิ้ง (`order_id`, target) โดยไม่ error
- ไม่ผ่านจะโยน `SchemaError` หรือ `SchemaErrors` (แปลงชนิดไม่ได้) ผู้เรียกต้องจับทั้งสองแบบ

ทดสอบ schema:

```bash
python src/test_schema.py      # แก้ payload ดีทีละจุด ต้องถูกปฏิเสธทุกกรณี -> พิมพ์ "schema checks ok"
python tests/check_cases.py    # tests/cases/good_* ต้องผ่าน, bad_* ต้องถูกปฏิเสธ
```

`tests/cases/` มี 6 ไฟล์: `good_normal`, `bad_missing_customer_lat` (ตัดฟิลด์ออกจริง), `bad_state_xx`, `bad_negative_weight`, `bad_outside_brazil` (lat = 40), `bad_wrong_type` (`n_items = "abc"`)

## การแบ่งข้อมูล

`time_split()` เรียงตามเวลาสั่งซื้อแล้วแบ่ง 70/15/15 = 66,724 / 14,298 / 14,299 order เพื่อให้โมเดลเรียนจากอดีตแล้วทดสอบกับอนาคต (train ครอบคลุม 15 ก.ย. 2016 – 16 เม.ย. 2018)

`delivery_days` เฉลี่ยลดลงตามเวลา: train 13.3 → val 10.4 → test 7.9 วัน แปลว่ามี drift ตามเวลาอยู่แล้วในข้อมูลจริง

## ข้อมูล demo: `demo_data/`

สร้างด้วย `python demo_data/make_demo_data.py` (`random_state=42` รันซ้ำได้ไฟล์เดิมทุกไบต์ ทุกไฟล์เล็กกว่า 2 MB) ทุกไฟล์มีคอลัมน์เหมือน CSV หลักรวม `delivery_days`

| ไฟล์ | แถว | วิธีสร้าง | สถานการณ์ | ผลที่คาด |
|---|---:|---|---|---|
| `normal_orders.csv` | 500 | สุ่มจาก test split | ปกติ | `monitor.py` exit 0 |
| `drift_north.csv` | 1,765 | `customer_state` ใน AC, AP, AM, PA, RO, RR, TO | **Data Drift** | `monitor.py` exit 2 |
| `drift_blackfriday.csv` | 3,264 | สั่งซื้อ 2017-11-20 ถึง 2017-11-27 | **Concept Drift** | `monitor.py` exit 3 |
| `bad_orders.csv` | 50 | 43 แถวปกติ + 7 แถวทำให้เสีย | ข้อมูลเสีย | `pipeline.py --data` exit 2 |

| ไฟล์ | `distance_km` (median) | `total_weight_g` (median) | `delivery_days` (เฉลี่ย / median) | `estimated_delivery_days` (เฉลี่ย) |
|---|---:|---:|---:|---:|
| ทั้ง dataset | – | – | 12.0 / – | – |
| `normal_orders.csv` | 371 | 588 | 8.2 / 7 | 18.2 |
| `drift_north.csv` | 2,379 | 651 | 22.1 / 20 | 37.1 |
| `drift_blackfriday.csv` | 472 | 900 | 16.2 / 13 | 22.1 |

- **`drift_north.csv`:** ลูกค้าภาคเหนืออยู่ไกลผู้ขาย (ส่วนใหญ่อยู่ SP) ระยะทาง median ~2,400 กม. เทียบ 371 กม. **การกระจายของ input เปลี่ยน**
- **`drift_blackfriday.csv`:** สัปดาห์ Black Friday 2017 order พุ่ง ขนส่งรับไม่ไหว ส่งเฉลี่ย 16.2 วัน เทียบ 12.0 วัน ระยะทางพอๆ เดิมแต่ส่งช้ากว่า **ความสัมพันธ์ input → เวลาส่งเปลี่ยน**

แถวที่ทำให้เสียใน `bad_orders.csv`:

| แถว (0-based) | คอลัมน์ | ค่า | ประเภท |
|---:|---|---|---|
| 4 | `total_weight_g` | `-500` | ค่าผิดช่วง |
| 42 | `customer_state` | `XX` | ค่าผิด |
| 20 | `customer_lat` | `40` | นอกบราซิล |
| 30 | `n_items` | `abc` | ชนิดผิด |
| 3 | `order_purchase_timestamp` | `not-a-date` | ชนิดผิด |
| 34 | `total_price` | ว่าง | ข้อมูลหาย |
| 47 | `seller_state` | ว่าง | ข้อมูลหาย |

ข้อมูลหายไม่ใช้ `customer_lat` เพราะ `load_splits` ตัดแถวที่ไม่มีพิกัดทิ้ง*ก่อน*ตรวจ schema แถวนั้นจะหายไปเงียบๆ demo จะไม่เห็นระบบหยุด
