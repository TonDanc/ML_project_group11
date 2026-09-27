# shipping_distance_duration.csv

สร้างจาก `compute_shipping_distance.py` โดยใช้ข้อมูลจาก `order_items_full_merged.csv`
(ซึ่ง merge มาจาก 4 ไฟล์ clean: customers, geolocation, products, sellers + order-level
features จาก `clean_loma.ipynb`)

**Grain:** 1 แถว = 1 order (เฉพาะ order ที่สถานะ `delivered` แล้ว, 95,824 แถว)
**เป้าหมาย:** ใช้เทรนโมเดลพยากรณ์ระยะเวลาจัดส่งสินค้า (`delivery_days`)

---

## คำอธิบายแต่ละคอลัมน์

| คอลัมน์ | ความหมาย | ใช้เป็น feature ได้ไหม |
|---|---|---|
| `order_id` | รหัส order (unique key) | ไม่ใช่ feature (identifier) |
| `customer_id` | รหัสลูกค้าของ order นี้ | ไม่ใช่ feature (identifier) |
| `customer_state` | รัฐ (province) ของลูกค้า เช่น SP, RJ, MG | ✅ ได้ (รู้ตั้งแต่ตอนสั่งซื้อ) |
| `customer_city` | เมืองของลูกค้า | ✅ ได้ แต่ cardinality สูง (~4,000 เมือง) ควร encode ระวัง |
| `customer_lat`, `customer_lng` | พิกัดของลูกค้า (median ของ zip code จาก geolocation) | ✅ ได้ — ใช้คู่กับ `distance_km` ให้โมเดลเห็นตำแหน่งจริง ไม่ใช่แค่ระยะทางตัวเลขเดียว |
| `seller_state` | รัฐของผู้ขาย | ✅ ได้ |
| `seller_lat`, `seller_lng` | พิกัดของผู้ขาย | ✅ ได้ |
| `distance_km` | ระยะทางเส้นตรง (haversine) จากผู้ขายถึงลูกค้า | ✅ ได้ — **เป็นเส้นตรง ไม่ใช่ระยะทางถนนจริง** ถ้า order มีหลาย seller ใช้ seller ที่ไกลสุด (ดูหมายเหตุด้านล่าง) |
| `n_sellers` | จำนวนผู้ขายที่ไม่ซ้ำกันใน order นี้ | ✅ ได้ — ส่วนใหญ่เป็น 1, มีส่วนน้อย (1.3%) ที่ >1 |
| `n_items` | จำนวนชิ้นสินค้าใน order | ✅ ได้ |
| `total_price` | ราคาสินค้ารวมทั้ง order (บาทบราซิล) | ✅ ได้ |
| `total_freight` | ค่าส่งรวมทั้ง order | ✅ ได้ |
| `total_weight_g` | น้ำหนักสินค้ารวมทั้ง order (กรัม) | ✅ ได้ |
| `order_purchase_timestamp` | วันเวลาที่กดสั่งซื้อ | ใช้ดึง feature เพิ่มได้ (day-of-week, เดือน, ฤดูกาล) ไม่ควรใช้ raw timestamp ตรงๆ |
| `order_estimated_delivery_date` | วันที่ Olist **ประเมิน**ไว้ตอนสั่งซื้อว่าจะได้รับสินค้า | รู้ตั้งแต่ตอนซื้อ ใช้ได้ แต่ปกติแนะนำใช้ `estimated_delivery_days` (ตัวเลขวันแทน) มากกว่า raw date |
| `order_delivered_customer_date` | วันที่ลูกค้า**ได้รับสินค้าจริง** | ❌ **ห้ามใช้เป็น feature** — เป็นวัตถุดิบที่ใช้คำนวณ `delivery_days` (target) โดยตรง เก็บไว้แค่เพื่อตรวจสอบย้อนหลัง |
| `delivery_days` | = `order_delivered_customer_date` − `order_purchase_timestamp` (วัน) | 🎯 **นี่คือ target** ไม่ใช่ feature |
| `same_state` | 1 ถ้า `customer_state == seller_state`, ไม่งั้น 0 | ✅ ได้ |
| `estimated_delivery_days` | = `order_estimated_delivery_date` − `order_purchase_timestamp` (วัน) | ✅ ได้ — เป็น "ค่าเดา" ของ Olist เองที่รู้ตั้งแต่ตอนซื้อ มักเป็น feature ที่ทรงพลัง |

---

## ⚠️ Data leakage ที่ต้องระวัง

**ห้ามใช้เป็น feature เด็ดขาด:** `order_delivered_customer_date`, และคอลัมน์ใดๆ ที่คำนวณ
มาจากวันที่ได้รับสินค้าจริง (เช่น `late_days`, `is_late`, `review_score` ในไฟล์ต้นทาง
`order_items_full_merged.csv` — ไม่ได้เอามารวมในไฟล์นี้แล้วด้วยเหตุผลนี้) เพราะข้อมูลพวกนี้
รู้ได้ก็ต่อเมื่อจัดส่งเสร็จแล้วเท่านั้น ถ้าใส่เป็น feature จะเท่ากับให้โมเดลเห็นคำตอบล่วงหน้า

## ปัญหาข้อมูลที่ทราบอยู่แล้ว (ไม่ได้แก้/impute เอง)

1. **503 orders มี `distance_km` เป็น NaN** — customer หรือ seller บางรายมี zip code
   ที่ไม่ตรงกับ zip ไหนเลยใน `geolocation` (291 orders ฝั่ง customer, 217 ฝั่ง seller)
   ต้องตัดสินใจตอนเทรนโมเดลว่าจะ drop หรือ impute
2. **1,261 orders (1.3%) มีมากกว่า 1 seller** — เลือกใช้ seller ที่ไกลจากลูกค้าที่สุดเป็น
   ตัวแทนทั้ง `distance_km`, `seller_lat`, `seller_lng`, `seller_state` (สมมติฐาน: การจัดส่ง
   จะช้าตาม seller ที่ไกลที่สุด) — ไม่ได้เฉลี่ยหรือรวมข้อมูลจากทุก seller
3. **`distance_km` เป็นระยะทางเส้นตรง (haversine)** ไม่ใช่ระยะทางถนน/เส้นทางขนส่งจริง
   ถ้าต้องการแม่นยำกว่านี้ต้องมีข้อมูลเส้นทาง/ผู้ให้บริการขนส่งซึ่งไม่มีใน dataset นี้
