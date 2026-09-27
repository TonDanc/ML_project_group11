# สินค้าจะมาถึงเมื่อไหร่ — พยากรณ์ระยะเวลาจัดส่ง (Olist)

พยากรณ์ `delivery_days` (จำนวนวันตั้งแต่สั่งซื้อจนลูกค้าได้รับของ) เป็นงาน Regression
ใช้ข้อมูล [Olist Brazilian E-commerce](https://kaggle.com/olistbr/brazilian-ecommerce)

## วิธีรัน

```bash
pip install -r requirements.txt
python src/test_schema.py   # เช็คว่า schema ปฏิเสธข้อมูลเสียได้
python src/train.py         # เทรนโมเดล -> models/model.joblib
```

รันจากโฟลเดอร์หลักของ repo เพราะ path ข้อมูลเขียนแบบ relative

## โครงสร้าง

```
raw_data + Data prepair/   ข้อมูลดิบ + notebook/สคริปต์ทำความสะอาด
cleaned_data/              ข้อมูลที่ clean แล้ว
  feature extraction/      shipping_distance_duration.csv (1 แถว = 1 order) <- ใช้เทรน
src/                       โค้ดโมเดล (ด้านล่าง)
models/                    โมเดลที่เทรนแล้ว (ไม่ commit, สร้างใหม่ด้วย train.py)
```

## ไฟล์ใน `src/`

### `schema.py` — ตรวจสอบข้อมูลขาเข้า (Pandera)

กำหนด `input_schema` สำหรับตรวจข้อมูล 1 order ก่อนส่งเข้าโมเดล ใช้ schema เดียวกันทั้งตอนเทรนและตอนทำ API

| คอลัมน์ | กฎ |
|---|---|
| `customer_state`, `seller_state` | ต้องเป็นรหัสรัฐบราซิล 27 รัฐ (`SP`, `RJ`, ...) |
| `customer_lat/lng`, `seller_lat/lng` | ต้องอยู่ในกรอบประเทศบราซิล (lat -34..6, lng -74..-34) |
| `n_sellers` | 1–20 |
| `n_items` | 1–100 |
| `total_price` | > 0 |
| `total_freight` | ≥ 0 |
| `total_weight_g` | 0–500,000 |
| `estimated_delivery_days` | 0–200 |
| `order_purchase_timestamp` | ต้องแปลงเป็นวันเวลาได้ |

- ทุกคอลัมน์ห้ามเป็นค่าว่าง และห้ามขาดคอลัมน์ใดคอลัมน์หนึ่ง
- `coerce=True` จะแปลงชนิดข้อมูลให้เอง เช่น `"12"` เป็น `12` ถ้าแปลงไม่ได้ถือว่าไม่ผ่าน
- `strict='filter'` จะตัดคอลัมน์เกินทิ้ง เช่น `order_id` และ target ไม่ทำให้ error
- ข้อมูลไม่ผ่านจะโยน `pandera.errors.SchemaError` หรือ `SchemaErrors` (กรณีแปลงชนิดไม่ได้) ตอนทำ API ต้อง catch ทั้งสองแบบ

### `train.py` — เทรนโมเดล baseline

ลำดับการทำงาน

1. โหลด `cleaned_data/feature extraction/shipping_distance_duration.csv`
2. ตัด 503 แถวที่ไม่มีพิกัด (zip code ไม่ตรงกับตาราง geolocation) ไม่ impute เพราะตอนใช้งานจริง payload แบบนี้ก็ไม่ผ่าน schema อยู่แล้ว
3. ตรวจข้อมูลด้วย `input_schema` ถ้าไม่ผ่านสคริปต์จะหยุดก่อนเทรน
4. แบ่งข้อมูลตามเวลาสั่งซื้อ (`time_split`) เป็น train/val/test 70/15/15 เพื่อให้โมเดลเรียนจากอดีตแล้วทดสอบกับอนาคต
5. เทรน 3 โมเดลโดยไม่ทำ Hyperparameter Tuning:
   - `DummyRegressor` ทายค่า median ทุกครั้ง ใช้เป็นเกณฑ์ขั้นต่ำ โมเดลจริงต้องชนะตัวนี้ให้ได้
   - `LinearRegression`
   - `HistGradientBoostingRegressor(loss='absolute_error')` ปรับให้ MAE ต่ำสุดโดยตรง เหมาะกับ target ที่เบ้ขวา (ส่วนใหญ่ 7–13 วัน แต่ค่าสูงสุดถึง 208 วัน)
6. พิมพ์ MAE/RMSE เทียบกับค่าประมาณเดิมของ Olist (`estimated_delivery_days`) ซึ่งใช้แทน "โมเดลปัจจุบัน"
7. บันทึก HistGradientBoosting เป็น `models/model.joblib` (ขนาดประมาณ 0.4 MB)

ฟังก์ชันหลัก

- `add_features(df)` สร้างฟีเจอร์จากข้อมูลดิบ ได้แก่ `distance_km` (ระยะทางเส้นตรงแบบ haversine), `same_state`, `purchase_dow`, `purchase_month` และ `purchase_hour`
- `make_pipeline(model)` รวม `add_features`, one-hot encoding ของรัฐ และโมเดล ไว้ใน sklearn `Pipeline` ตัวเดียว
- `time_split(df)` แบ่งข้อมูลตามเวลา
- `report(...)` พิมพ์ MAE/RMSE

**ป้องกัน Training-Serving Skew:** การแปลงข้อมูลทั้งหมดอยู่ใน Pipeline ที่บันทึกลงไฟล์ `.joblib` เดียว
ตอนทำ API ให้ส่งข้อมูลดิบที่ผ่าน schema เข้า `pipe.predict()` ได้เลย ไม่ต้องเขียนโค้ดแปลงข้อมูลซ้ำ

ผลลัพธ์ล่าสุด (MAE หน่วยเป็นวัน)

| โมเดล | val | test |
|---|---|---|
| ค่าประมาณของ Olist | 15.00 | 10.79 |
| Dummy (ทาย median) | 5.67 | 5.06 |
| Linear Regression | 5.38 | 4.96 |
| Random Forest (รุ่นแรก, เลิกใช้แล้ว) | 4.62 | 4.07 |
| **HistGradientBoosting (absolute_error)** | **4.09** | **3.39** |

**อ่านผลอย่างไร**
- ค่าประมาณของ Olist ตั้งใจเผื่อเวลาไว้เยอะ (ส่งถึงก่อนกำหนดเกือบทุก order) จึงไม่ใช่ตัวเทียบที่ยุติธรรม ตัวเทียบที่ถูกต้องคือ Dummy
- HistGradientBoosting ทำ MAE ต่ำกว่า Dummy ประมาณ 33% และต่ำกว่า Random Forest ประมาณ 17% เทรนเสร็จในไม่กี่วินาที และไฟล์โมเดลเล็กกว่า Random Forest ประมาณ 100 เท่า
- ประมาณ 30% ของ order ใน test ส่งถึงช้ากว่าที่โมเดลทำนาย เพราะการปรับ MAE ให้ต่ำสุดคือการทายค่ากลาง ถ้าธุรกิจอยากลดโอกาสส่งช้ากว่าที่แจ้ง ให้เปลี่ยนเป็น `loss='quantile'` เช่น `quantile=0.8`
- ค่า delivery_days เฉลี่ยลดลงตามเวลา (train 13.3 → val 10.4 → test 7.9 วัน) แปลว่ามี drift ตามช่วงเวลาอยู่แล้ว ควรเทรนใหม่เป็นระยะ

### `test_schema.py` — เช็คว่า schema ทำงาน

สร้าง payload ที่ถูกต้อง 1 แถว แล้วแก้ทีละจุดเพื่อยืนยันว่า schema ปฏิเสธข้อมูลเหล่านี้ได้จริง:
ขาดคอลัมน์, ค่า null, รหัสรัฐผิด, น้ำหนักติดลบ, พิกัดนอกบราซิล และชนิดข้อมูลผิด
รันผ่านจะพิมพ์ `schema checks ok` ถ้าไม่ผ่านจะเกิด `AssertionError`

## สิ่งที่ยังไม่ได้ทำ

- ยังไม่มี `customer_zip_code` ใน schema ต้องเพิ่มขั้นตอนแปลง zip เป็นพิกัดตอนทำ API
- ยังไม่บันทึก metrics ลงไฟล์ จะทำตอนตั้ง MLflow
- ยังไม่แยกช่วง Black Friday ออกไปใช้ทดสอบ Concept Drift
