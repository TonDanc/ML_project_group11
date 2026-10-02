# demo_data — ข้อมูลจำลองสำหรับ demo, monitoring และ pipeline

สร้างจาก `make_demo_data.py` โดยอ่าน `cleaned_data/feature extraction/shipping_distance_duration.csv`
(ตามสัญญาข้อ C ใน [GUIDE.md](../GUIDE.md))

```bash
python demo_data/make_demo_data.py    # รันจากโฟลเดอร์หลักของ repo
```

- ใช้ `random_state=42` รันซ้ำกี่ครั้งก็ได้ไฟล์เหมือนเดิมทุกไบต์
- ตัดแถวที่ไม่มีพิกัดออกก่อน (503 แถว) เหมือน `train.load_splits` เหลือ 95,321 แถว
- **ทุกไฟล์มีคอลัมน์เหมือน `shipping_distance_duration.csv`** รวม `delivery_days` (target) ด้วย
  ดูความหมายคอลัมน์ได้ที่ [README_shipping_distance_duration.md](../cleaned_data/feature%20extraction/README_shipping_distance_duration.md)
- ทุกไฟล์เล็กกว่า 2 MB (สคริปต์ assert ไว้)

---

## ไฟล์ทั้งหมด

| ไฟล์ | แถว | วิธีสร้าง | สถานการณ์ | ใช้โดย |
|---|---:|---|---|---|
| `normal_orders.csv` | 500 | สุ่มจาก test split (15% ท้ายตามเวลาสั่งซื้อ ตรงกับ `time_split`) | ข้อมูลปกติ ไม่มี drift | monitor, demo |
| `drift_north.csv` | 1,765 | `customer_state` อยู่ใน `AC, AP, AM, PA, RO, RR, TO` (ภาคเหนือ) | **Data Drift** ระยะทางไกลกว่าปกติมาก | monitor |
| `drift_blackfriday.csv` | 3,264 | `order_purchase_timestamp` อยู่ระหว่าง 2017-11-20 ถึง 2017-11-27 | **Concept Drift** พัสดุมาช้ากว่าปกติ | monitor |
| `bad_orders.csv` | 50 | สุ่ม 50 แถวปกติ แล้วทำให้ 7 แถวเสียโดยตั้งใจ | **ข้อมูลเสีย/หาย** ต้องถูก Pandera ปฏิเสธ | pipeline, demo |

## สถิติเทียบกัน

| ไฟล์ | `distance_km` (median) | `total_weight_g` (median) | `delivery_days` (เฉลี่ย / median) | `estimated_delivery_days` (เฉลี่ย) |
|---|---:|---:|---:|---:|
| ข้อมูลทั้งหมด | – | – | 12.0 / – | – |
| `normal_orders.csv` | 371 | 588 | 8.2 / 7 | 18.2 |
| `drift_north.csv` | 2,379 | 651 | 22.1 / 20 | 37.1 |
| `drift_blackfriday.csv` | 472 | 900 | 16.2 / 13 | 22.1 |

ตัวเลขทั้งหมดมาจากข้อมูลจริง ไม่ได้ปรับแต่งให้ดู drift

---

## รายละเอียดแต่ละสถานการณ์

### `drift_north.csv` — Data Drift

ลูกค้าภาคเหนืออยู่ห่างจากผู้ขาย (ส่วนใหญ่อยู่ SP) มาก ระยะทาง median ประมาณ 2,400 กม.
เทียบกับ 371 กม. ของข้อมูลปกติ **การกระจายของ input เปลี่ยน** จึงควรถูกจับได้ด้วย KS/PSI
บน `distance_km` (เกณฑ์ในสัญญา D: PSI > 0.2 หรือ KS p-value < 0.01)

### `drift_blackfriday.csv` — Concept Drift

ช่วงสัปดาห์ Black Friday 2017 (24 พ.ย.) ปริมาณ order พุ่งขึ้น ระบบขนส่งรับไม่ไหว
พัสดุใช้เวลาเฉลี่ย 16.2 วัน เทียบกับ 12.0 วันของทั้ง dataset **ความสัมพันธ์ระหว่าง input กับ
เวลาส่งจริงเปลี่ยน** (ระยะทางพอๆ กับปกติ แต่ส่งช้ากว่า) จึงควรเห็นเป็น MAE ของ `@champion` ที่สูงขึ้น

> ยังไม่ได้ยืนยันว่า MAE เกินเกณฑ์ 2 วันจริงหรือไม่ ให้ดูจากผล `monitor.py` แล้วรายงานตามจริง

### `bad_orders.csv` — ข้อมูลเสีย/หาย

43 แถวเป็นข้อมูลปกติ อีก 7 แถวถูกทำให้เสียคนละแบบ (สคริปต์พิมพ์เลขแถวออกมาตอนรัน):

| แถว (0-based) | คอลัมน์ | ค่าที่ใส่ | ประเภท | กฎ schema ที่ละเมิด |
|---:|---|---|---|---|
| 4 | `total_weight_g` | `-500` | ค่าผิด | ต้องอยู่ใน 0–500,000 |
| 42 | `customer_state` | `XX` | ค่าผิด | ต้องเป็นรหัสรัฐบราซิล 27 รัฐ |
| 20 | `customer_lat` | `40` | ค่าผิด | ต้องอยู่ในกรอบบราซิล (-34..6) |
| 30 | `n_items` | `abc` | ชนิดข้อมูลผิด | แปลงเป็น int ไม่ได้ |
| 3 | `order_purchase_timestamp` | `not-a-date` | ชนิดข้อมูลผิด | แปลงเป็นวันเวลาไม่ได้ |
| 34 | `total_price` | ว่าง | ข้อมูลหาย | ห้ามเป็นค่าว่าง |
| 47 | `seller_state` | ว่าง | ข้อมูลหาย | ห้ามเป็นค่าว่าง |

**ทำไมข้อมูลหายไม่ใช้ `customer_lat`:** `load_splits` ตัดแถวที่ไม่มี lat ทิ้ง*ก่อน*ตรวจ schema
ถ้าทำให้ lat หาย แถวนั้นจะหายไปเงียบๆ ไม่ถูก Pandera จับ demo จะไม่เห็นว่าระบบหยุด

---

## วิธีใช้

```bash
python src/monitor.py --current demo_data/normal_orders.csv       # คาดว่า exit 0 (ไม่มี drift)
python src/monitor.py --current demo_data/drift_north.csv         # คาดว่า exit 2 (Data Drift)
python src/monitor.py --current demo_data/drift_blackfriday.csv   # คาดว่า exit 3 (Concept Drift)
python src/pipeline.py --data demo_data/bad_orders.csv            # หยุดที่ validate, exit 2
```

ท้ายสคริปต์มีการตรวจอัตโนมัติ: 3 ไฟล์แรกต้องผ่าน `input_schema` และ `bad_orders.csv` ต้องถูกปฏิเสธ
ถ้าไม่เป็นตามนี้สคริปต์จะ error
