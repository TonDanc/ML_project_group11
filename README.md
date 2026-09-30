# สินค้าจะมาถึงเมื่อไหร่ — พยากรณ์ระยะเวลาจัดส่ง (Olist)

พยากรณ์ `delivery_days` (จำนวนวันตั้งแต่สั่งซื้อจนลูกค้าได้รับของ) เป็นงาน Regression
ใช้ข้อมูล [Olist Brazilian E-commerce](https://kaggle.com/olistbr/brazilian-ecommerce)

## โจทย์

**Problem:** ลูกค้าไม่ทราบว่าสินค้าจะมาถึงเมื่อไหร่ ระยะเวลาที่แพลตฟอร์มแจ้งในปัจจุบันเผื่อเวลามากเกินไป
(คลาดเคลื่อนเฉลี่ยประมาณ 11 วัน) ทำให้ลูกค้าอาจเปลี่ยนใจไม่ซื้อ และเมื่อสินค้ามาช้ากว่าที่คาด
ลูกค้าจะร้องเรียนและให้คะแนนร้านค้าต่ำ

**Stakeholder:** ลูกค้า (เห็น ETA ที่ใกล้ความจริง), ผู้ขาย (ได้คะแนนรีวิวดีขึ้นเมื่อส่งตรงตามที่แจ้ง), ฝ่ายบริการลูกค้า (รับข้อร้องเรียนเรื่องส่งช้าน้อยลง)

**ML Solution:** ใช้ข้อมูลที่รู้ตั้งแต่ตอนสั่งซื้อ (ตำแหน่งผู้ซื้อและผู้ขาย ระยะทาง น้ำหนัก ราคา ค่าส่ง เวลาที่สั่ง)
ทำนายจำนวนวันจัดส่งจริงของแต่ละ order เพื่อแสดง ETA ตอน Checkout

**Business Value:**
- เพิ่ม Checkout Conversion Rate เพราะไม่แสดงเวลาส่งนานเกินจริง
- ลดข้อร้องเรียนเรื่องส่งช้ากว่าที่แจ้ง
- ประโยชน์รอง: นำผลทำนายของ order ที่เข้ามาแล้วมารวมรายรัฐและรายวัน เพื่อให้เห็นแนวโน้มปริมาณพัสดุที่จะเข้าแต่ละพื้นที่ในอีกไม่กี่วันข้างหน้า

**ทำไมตัดเรื่อง "บริษัทขนส่งประเมินทรัพยากรล่วงหน้า" ออกจาก Problem:**
dataset ไม่มีข้อมูลบริษัทขนส่ง ความจุรถ หรือเส้นทาง และการวางแผนทรัพยากรต้องพยากรณ์ปริมาณงานรายวันรายพื้นที่
ซึ่งเป็นโจทย์อนุกรมเวลา ไม่ใช่การทำนายเวลาส่งรายออเดอร์ที่โมเดลนี้ทำ

## ข้อมูลที่ใช้เทรน

ใช้ `cleaned_data/feature extraction/shipping_distance_duration.csv` ตามที่มีอยู่ ไม่ต้องแก้ไข

- **คอลัมน์ที่ห้ามใช้ถูกกรองอัตโนมัติ:** `order_delivered_customer_date` (ถ้าเอาเข้าโมเดลจะรั่วคำตอบ) และ id ต่างๆ ถูก schema (`strict='filter'`) ตัดทิ้งก่อนเข้าโมเดล
- **zip code ไม่ต้องอยู่ใน dataset:** โมเดลใช้พิกัด ส่วนการรับ zip แล้วแปลงเป็นพิกัดเป็นงานของ API โดยใช้ `cleaned_data/olist_geolocation_dataset_clean.csv`
- **ข้อควรระวังตอนทำ API:** ตาราง geolocation มีหลายแถวต่อ 1 zip ตอนสร้าง dataset ใช้ **median ของพิกัดต่อ zip** ตอนให้บริการต้องแปลง zip ด้วยวิธีเดียวกัน ไม่งั้นจะเกิด Training-Serving Skew

## วิธีรัน

### แบบ Docker (เครื่องเปล่า มีแค่ Docker)

```bash
docker compose up -d mlflow        # MLflow UI: http://localhost:5050
docker compose run --rm train      # เทรน -> log ลง MLflow -> register @challenger -> ด่านตรวจ -> @champion
docker compose up -d api           # API ใช้โมเดล @champion: http://localhost:8000 (/docs, /health)
```

ใน container ไม่มี .git ต้องส่งเวอร์ชันโค้ดเข้าไปเอง ไม่งั้น run จะบันทึก `git_commit=unknown`
- bash: `GIT_COMMIT=$(git rev-parse HEAD) docker compose run --rm train`
- PowerShell: `$env:GIT_COMMIT = git rev-parse HEAD; docker compose run --rm train`

### แบบรันในเครื่อง (Python 3.11)

```bash
pip install -r requirements.txt
python src/test_schema.py        # เช็คว่า schema ปฏิเสธข้อมูลเสียได้
python src/train.py              # log ลง ./mlflow.db (ไม่ต้องเปิด server)
python src/registry.py promote
mlflow ui --backend-store-uri sqlite:///mlflow.db   # ดูผล
```

รันจากโฟลเดอร์หลักของ repo เพราะ path ข้อมูลเขียนแบบ relative
ถ้าตั้ง `MLFLOW_TRACKING_URI` ไว้ ทุกสคริปต์จะใช้ server นั้นแทน `mlflow.db`

## โครงสร้าง

```
raw_data + Data prepair/   ข้อมูลดิบ + notebook/สคริปต์ทำความสะอาด
cleaned_data/              ข้อมูลที่ clean แล้ว
  feature extraction/      shipping_distance_duration.csv (1 แถว = 1 order) <- ใช้เทรน
src/                       โค้ดโมเดล (ด้านล่าง)
docker-compose.yml         mlflow (server), train (job), api
```

โมเดลที่เทรนแล้วอยู่ใน MLflow Registry ไม่ได้ commit ลง git

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
5. เทรน 4 โมเดล แต่ละตัวเป็น 1 run ใน MLflow (experiment `delivery_eta`):
   - `dummy_median` (`DummyRegressor`) ทายค่า median ทุกครั้ง ใช้เป็นเกณฑ์ขั้นต่ำ โมเดลจริงต้องชนะตัวนี้ให้ได้
   - `linear_regression`
   - `hgb_default`: `HistGradientBoostingRegressor(loss='absolute_error')` ปรับให้ MAE ต่ำสุดโดยตรง เหมาะกับ target ที่เบ้ขวา (ส่วนใหญ่ 7–13 วัน แต่ค่าสูงสุดถึง 208 วัน)
   - `hgb_bigger`: HGB ที่ใหญ่ขึ้น (`max_iter=300, learning_rate=0.05, max_leaf_nodes=63`) เพื่อทดสอบว่า tuning ช่วยไหม
6. พิมพ์ MAE ของค่าประมาณเดิมของ Olist (`estimated_delivery_days`) ไว้อ้างอิง
7. เลือกตัวที่ **val** MAE ต่ำสุด (ไม่เลือกจาก test) แล้วลงทะเบียนเป็นเวอร์ชันใหม่ของ `delivery_eta` พร้อมติดป้าย `@challenger`

ตั้ง `CANDIDATES=dummy_median,linear_regression` เพื่อเทรนเฉพาะบางตัวได้ (ใช้สร้างโมเดล "รุ่นเก่า" ตอนสาธิต rollback)

ฟังก์ชันหลัก

- `add_features(df)` สร้างฟีเจอร์จากข้อมูลดิบ ได้แก่ `distance_km` (ระยะทางเส้นตรงแบบ haversine), `same_state`, `purchase_dow`, `purchase_month` และ `purchase_hour`
- `make_pipeline(model)` รวม `add_features`, one-hot encoding ของรัฐ และโมเดล ไว้ใน sklearn `Pipeline` ตัวเดียว
- `time_split(df)` แบ่งข้อมูลตามเวลา
- `load_splits()` โหลด ตรวจ schema และแบ่งข้อมูล (`registry.py` ใช้ตัวเดียวกันเพื่อให้ได้ test ชุดเดียวกัน)

**ป้องกัน Training-Serving Skew:** การแปลงข้อมูลทั้งหมดอยู่ใน Pipeline ตัวเดียวที่บันทึกลง MLflow (พร้อมไฟล์ `features.py`)
ตอนทำ API ให้ส่งข้อมูลดิบที่ผ่าน schema เข้า `pipe.predict()` ได้เลย ไม่ต้องเขียนโค้ดแปลงข้อมูลซ้ำ

ผลลัพธ์ล่าสุด (MAE หน่วยเป็นวัน)

| โมเดล | val | test |
|---|---|---|
| ค่าประมาณของ Olist | 15.00 | 10.79 |
| Dummy (ทาย median) | 5.67 | 5.06 |
| Linear Regression | 5.38 | 4.96 |
| Random Forest (รุ่นแรก, เลิกใช้แล้ว) | 4.62 | 4.07 |
| **HistGradientBoosting (absolute_error)** | **4.09** | **3.39** |

**ทำไมต้องมี DummyRegressor**

Dummy คือโมเดลที่ไม่เรียนรู้อะไรเลย แค่ทายค่า median ของ train (11 วัน) ให้ทุก order ใช้เป็นเกณฑ์ขั้นต่ำ

- MAE ตัวเลขเดียวบอกไม่ได้ว่าดีหรือไม่ดี ต้องมีตัวเทียบถึงจะรู้ว่าโมเดลเรียนรู้อะไรไปจริง
- ค่าประมาณของ Olist ใช้เทียบไม่ได้ เพราะเผื่อเวลาเยอะจน Dummy ยังชนะ
- ตรงกับเกณฑ์วิชาที่ต้องมี Baseline และการทดลองเปรียบเทียบ
- ใช้จับบั๊กได้ ถ้าโมเดลจริงได้ MAE พอๆ กับ Dummy แปลว่าฟีเจอร์หาย ข้อมูลเสีย หรือ pipeline ผิด ใช้เป็นด่านตรวจใน Evaluator ได้
- ใช้ median ไม่ใช้ mean เพราะวัดผลด้วย MAE (ค่าคงที่ที่ทำให้ MAE ต่ำสุดคือ median) และ target เบ้ขวา mean จะถูกค่าสูงผิดปกติดึงขึ้น

**ทำไมเลือก HistGradientBoosting แทน Random Forest**

| | Random Forest | HistGradientBoosting |
|---|---|---|
| test MAE | 4.07 | 3.39 |
| เวลาเทรน | ~1.5 นาที | ~2 วินาที |
| ขนาดไฟล์โมเดล | 47 MB | 0.4 MB |

ไฟล์เล็กและทำนายเร็ว ช่วยให้ผ่าน Gating Metric เรื่อง Latency < 200 ms ตอนทำ API
ใช้ `loss='absolute_error'` เพื่อให้โมเดลปรับ MAE ต่ำสุดโดยตรง ค่าที่สูงผิดปกติจึงไม่ดึงผลทำนายไปมาก
และต้องตั้ง `OneHotEncoder(sparse_output=False)` เพราะ HistGradientBoosting รับข้อมูลแบบ sparse ไม่ได้

**อ่านผลอย่างไร**
- ค่าประมาณของ Olist ตั้งใจเผื่อเวลาไว้เยอะ (ส่งถึงก่อนกำหนดเกือบทุก order) จึงไม่ใช่ตัวเทียบที่ยุติธรรม ตัวเทียบที่ถูกต้องคือ Dummy
- HistGradientBoosting ทำ MAE ต่ำกว่า Dummy ประมาณ 33% และต่ำกว่า Random Forest ประมาณ 17% เทรนเสร็จในไม่กี่วินาที และไฟล์โมเดลเล็กกว่า Random Forest ประมาณ 100 เท่า
- ประมาณ 30% ของ order ใน test ส่งถึงช้ากว่าที่โมเดลทำนาย เพราะการปรับ MAE ให้ต่ำสุดคือการทายค่ากลาง ถ้าธุรกิจอยากลดโอกาสส่งช้ากว่าที่แจ้ง ให้เปลี่ยนเป็น `loss='quantile'` เช่น `quantile=0.8`
- ค่า delivery_days เฉลี่ยลดลงตามเวลา (train 13.3 → val 10.4 → test 7.9 วัน) แปลว่ามี drift ตามช่วงเวลาอยู่แล้ว ควรเทรนใหม่เป็นระยะ

### MLflow — Experiment Tracking + Model Registry

**ทุก run บันทึกครบ 6 อย่าง**

| สิ่งที่ต้องบันทึก | เก็บที่ไหนใน run |
|---|---|
| เวอร์ชันโค้ด | tag `git_commit` |
| เวอร์ชันข้อมูล | param `data_md5` (md5 ของ CSV), `data_rows`, `n_train/n_val/n_test`, `split` |
| ไฮเปอร์พารามิเตอร์ | params ทั้งหมดของโมเดล (`get_params()`) |
| ตัวชี้วัด | `val_mae`, `val_rmse`, `test_mae`, `test_rmse` |
| ไฟล์ผลลัพธ์ | โมเดล (`model.skops`), `features.py`, `input_example.json` |
| สภาพแวดล้อม | tag `python`, `platform` และ `requirements.txt` / `conda.yaml` ที่ MLflow สร้างคู่กับโมเดล |

เปรียบเทียบข้ามการทดลอง: เปิด MLflow UI → experiment `delivery_eta` → เลือกหลาย run → Compare

**ผลการทดลองและการตัดสินใจ**

| run | val MAE | test MAE | ตัดสินใจ |
|---|---|---|---|
| dummy_median | 5.671 | 5.057 | เกณฑ์ขั้นต่ำ |
| linear_regression | 5.377 | 4.962 | ดีกว่า dummy นิดเดียว ความสัมพันธ์ไม่เป็นเส้นตรง |
| **hgb_default** | **4.086** | **3.389** | **เลือกตัวนี้** |
| hgb_bigger | 4.092 | 3.412 | ใหญ่ขึ้น ช้าขึ้น แต่ไม่ดีขึ้น → tuning ไม่คุ้ม |

**`registry.py` — สถานะโมเดลและด่านตรวจ**

สถานะเก็บเป็น alias ของ MLflow: `@champion` = ตัวที่ API ใช้อยู่, `@challenger` = ตัวใหม่ล่าสุดที่รอตรวจ
และ tag ของแต่ละเวอร์ชัน: `gate` (passed/failed), `gate_reason`, `test_mae`, `p95_ms`, `rolled_back`

```bash
python src/registry.py status          # ดูทุกเวอร์ชัน
python src/registry.py promote         # ด่านตรวจ: ผ่าน -> @champion, ไม่ผ่าน -> exit 1 (ใช้ใน CI ได้)
python src/registry.py rollback [VER]  # @champion ย้อนไปเวอร์ชันก่อนหน้าที่เคยผ่านด่าน (หรือ VER)
```

ถ้าใช้ Docker ให้ขึ้นต้นด้วย `docker compose run --rm train` เช่น `docker compose run --rm train python src/registry.py status`

ด่านตรวจก่อนอนุมัติ (Gating Metric) วัดบน test ชุดเดียวกันทั้งตัวใหม่และตัวเดิม ต้องผ่านทุกข้อ:
- MAE ต่ำกว่า dummy (median)
- MAE ต่ำกว่า `@champion` ตัวเดิมอย่างน้อย 5%
- p95 latency ของการทำนาย 1 order < 200 ms

API โหลด `@champion` ตอนเริ่มทำงาน หลัง promote/rollback ให้ `docker compose restart api`
`/health` และ `/predict` บอกเวอร์ชันโมเดลที่ใช้อยู่

**สาธิต (เริ่มจากว่าง: `docker compose down -v`)**

```bash
docker compose up -d mlflow
CANDIDATES=dummy_median,linear_regression docker compose run --rm train   # v1 = linear "รุ่นเก่า" -> ผ่าน -> @champion
docker compose run --rm train      # v2 = hgb, ดีกว่า v1 เกิน 5% -> ผ่าน -> @champion
docker compose run --rm train      # v3 = เทรนซ้ำข้อมูลเดิม ไม่ดีขึ้น 5% -> REJECTED (exit 1), API ยังใช้ v2
docker compose up -d api && curl localhost:8000/health    # version 2
docker compose run --rm train python src/registry.py rollback   # @champion v2 -> v1
docker compose restart api && curl localhost:8000/health  # version 1
```

PowerShell: บรรทัดที่ 2 ใช้ `$env:CANDIDATES = "dummy_median,linear_regression"; docker compose run --rm train`
แล้ว `$env:CANDIDATES = ""` ก่อนรันบรรทัดที่ 3 ไม่งั้นจะเทรนแค่ linear อีก และใช้ `curl.exe` แทน `curl`

ดูผลใน MLflow UI ที่ http://localhost:5050 (Experiments → `delivery_eta` เทียบ run, Models → `delivery_eta` ดูเวอร์ชันและ alias)

### `test_schema.py` — เช็คว่า schema ทำงาน

สร้าง payload ที่ถูกต้อง 1 แถว แล้วแก้ทีละจุดเพื่อยืนยันว่า schema ปฏิเสธข้อมูลเหล่านี้ได้จริง:
ขาดคอลัมน์, ค่า null, รหัสรัฐผิด, น้ำหนักติดลบ, พิกัดนอกบราซิล และชนิดข้อมูลผิด
รันผ่านจะพิมพ์ `schema checks ok` ถ้าไม่ผ่านจะเกิด `AssertionError`

## สิ่งที่ยังไม่ได้ทำ

- ตัดสินใจรูปแบบ input ของ API (โมเดลใช้พิกัดเสมอ ไม่ใช้ zip code):
  - ถ้า API รับพิกัดตรงๆ ใช้ schema ปัจจุบันได้เลย ส่วน Demo ข้อมูลเสียให้ส่ง payload ที่ขาด `customer_lat` แทน `customer_zip_code`
  - ถ้า API รับ zip code (ใกล้เคียงระบบจริงกว่า) API ต้องแปลง zip เป็นพิกัดด้วย median ต่อ zip ก่อนส่งเข้า schema และโมเดล
- ยังไม่แยกช่วง Black Friday ออกไปใช้ทดสอบ Concept Drift
- ทางเลือกเพื่อลดโอกาสส่งช้ากว่าที่แจ้ง (ถ้าทีมตัดสินใจทำ):
  - เปลี่ยนเป็น `loss='quantile', quantile=0.8`
  - หรือเทรน 2 ตัว (quantile 0.2 และ 0.8) แล้วแสดง ETA เป็นช่วงวันที่
- ฟีเจอร์ที่อาจช่วยให้แม่นขึ้น (อยู่นอกขอบเขต Baseline):
  - หมวดสินค้า
  - ค่าเฉลี่ยเวลาส่งในอดีตของ seller ต้องคำนวณจากข้อมูลก่อนวันสั่งเท่านั้น ไม่งั้นข้อมูลรั่ว
