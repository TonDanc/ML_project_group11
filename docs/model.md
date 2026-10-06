# โมเดล: เทรน ติดตามการทดลอง และทะเบียนโมเดล

## เทรน: `src/train.py`

1. `load_splits()` โหลด CSV → ตัด 503 แถวที่ไม่มีพิกัด → ตรวจ `input_schema` (ไม่ผ่าน = หยุดก่อนเทรน) → แบ่งตามเวลา 70/15/15 (ดู [data.md](data.md))
2. เทรน 4 โมเดล แต่ละตัวเป็น 1 run ใน MLflow experiment `delivery_eta`
3. พิมพ์ MAE ของค่าประมาณเดิมของ Olist (`estimated_delivery_days`) ไว้อ้างอิง
4. เลือกตัวที่ **val** MAE ต่ำสุด (ไม่เลือกจาก test เพราะ test เก็บไว้ให้ด่านตรวจ) ลงทะเบียนเป็นเวอร์ชันใหม่ของ `delivery_eta` พร้อม alias `@challenger`

| ชื่อ | โมเดล | ทำไมมี |
|---|---|---|
| `dummy_median` | `DummyRegressor(strategy='median')` | baseline ขั้นต่ำ โมเดลจริงต้องชนะ |
| `linear_regression` | `LinearRegression()` | baseline แบบเส้นตรง |
| `hgb_default` | `HistGradientBoostingRegressor(loss='absolute_error')` | ปรับ MAE ต่ำสุดโดยตรง เหมาะกับ target เบ้ขวา (ส่วนใหญ่ 7–13 วัน สูงสุด 208 วัน) |
| `hgb_bigger` | HGB `max_iter=300, learning_rate=0.05, max_leaf_nodes=63` | ทดสอบว่า tuning ช่วยไหม |

เทรนเฉพาะบางตัวได้ด้วย `CANDIDATES=dummy_median,linear_regression` (ใช้สร้างโมเดล "รุ่นเก่า" ตอนสาธิต rollback และใน CI)

**ฟีเจอร์ (`src/features.py`):** `add_features(df)` สร้าง `distance_km` (haversine), `same_state`, `purchase_dow`, `purchase_month`, `purchase_hour`

**กัน Training-Serving Skew:** `make_pipeline(model)` รวม `add_features` + one-hot ของรัฐ + โมเดล เป็น sklearn `Pipeline` ก้อนเดียว แล้ว log ทั้งก้อนลง MLflow API โหลดก้อนเดียวกันนี้แล้วส่งข้อมูลที่ผ่าน schema เข้า `predict()` ตรงๆ ไม่มีโค้ดแปลงข้อมูลซ้ำในฝั่ง API

## ผลการทดลองและการเลือกโมเดล

MAE หน่วยเป็นวัน

| run | val MAE | test MAE | ตัดสินใจ |
|---|---:|---:|---|
| ค่าประมาณของ Olist (อ้างอิง) | 15.00 | 10.79 | เผื่อเวลามากจนแพ้ dummy |
| `dummy_median` | 5.671 | 5.057 | เกณฑ์ขั้นต่ำ |
| `linear_regression` | 5.377 | 4.962 | ดีกว่า dummy นิดเดียว ความสัมพันธ์ไม่เป็นเส้นตรง |
| **`hgb_default`** | **4.086** | **3.389** | **เลือกตัวนี้** |
| `hgb_bigger` | 4.092 | 3.412 | ใหญ่และช้ากว่าแต่ไม่ดีขึ้น tuning ไม่คุ้ม |
| Random Forest (รุ่นแรก เลิกใช้) | 4.62 | 4.07 | |

**ทำไมต้องมี Dummy:** MAE ตัวเลขเดียวบอกไม่ได้ว่าดีหรือไม่ ต้องมีตัวเทียบ ค่าประมาณของ Olist ใช้เทียบไม่ได้เพราะเผื่อเวลาเยอะจน dummy ยังชนะ ถ้าโมเดลจริงได้ MAE พอๆ กับ dummy แปลว่าฟีเจอร์หาย ข้อมูลเสีย หรือ pipeline ผิด จึงใช้เป็นด่านตรวจได้ ใช้ median ไม่ใช้ mean เพราะค่าคงที่ที่ทำให้ MAE ต่ำสุดคือ median และ target เบ้ขวา

**ทำไม HistGradientBoosting แทน Random Forest:**

| | Random Forest | HistGradientBoosting |
|---|---:|---:|
| test MAE | 4.07 | 3.39 |
| เวลาเทรน | ~1.5 นาที | ~2 วินาที |
| ขนาดไฟล์โมเดล | 47 MB | 0.4 MB |

ไฟล์เล็กและทำนายเร็ว ช่วยให้ผ่าน gate เรื่อง latency ต้องตั้ง `OneHotEncoder(sparse_output=False)` เพราะ HGB รับ sparse ไม่ได้

**อ่านผล:**
- HGB ทำ MAE ต่ำกว่า dummy ~33% และต่ำกว่า Random Forest ~17%
- ~30% ของ order ใน test ส่งถึงช้ากว่าที่ทำนาย เพราะการลด MAE คือการทายค่ากลาง ถ้าธุรกิจอยากลดโอกาสส่งช้ากว่าที่แจ้ง ให้เปลี่ยนเป็น `loss='quantile', quantile=0.8` หรือเทรน quantile 0.2 กับ 0.8 แล้วแสดง ETA เป็นช่วง

## Experiment tracking (MLflow)

ทุก run บันทึกครบ 6 อย่าง:

| สิ่งที่ต้องบันทึก | เก็บที่ไหนใน run |
|---|---|
| เวอร์ชันโค้ด | tag `git_commit` (ใน Docker ไม่มี `.git` ต้องส่ง env `GIT_COMMIT` เข้าไป) |
| เวอร์ชันข้อมูล | param `data_md5`, `data_rows`, `n_train/n_val/n_test`, `split` |
| ไฮเปอร์พารามิเตอร์ | params ทั้งหมดจาก `model.get_params()` |
| ตัวชี้วัด | `val_mae`, `val_rmse`, `test_mae`, `test_rmse` |
| ไฟล์ผลลัพธ์ | `model.skops`, `code/features.py`, `input_example.json` |
| สภาพแวดล้อม | tag `python`, `platform` + `requirements.txt`, `conda.yaml`, `python_env.yaml` ที่ MLflow สร้างคู่โมเดล |

เทียบข้ามการทดลอง: MLflow UI (http://localhost:5050) → Experiments → `delivery_eta` → เลือกหลาย run → Compare

## Model registry และ gate: `src/registry.py`

**สถานะ** เก็บเป็น alias: `@champion` = ตัวที่ API ใช้, `@challenger` = ตัวใหม่ล่าสุดที่รอตรวจ
**ประวัติ** เก็บเป็น tag ของแต่ละเวอร์ชัน: `gate` (passed/failed), `gate_reason`, `test_mae`, `p95_ms`, `rolled_back`

```bash
python src/registry.py status          # ดูทุกเวอร์ชัน alias และผล gate
python src/registry.py promote         # gate: ผ่าน -> @champion, ไม่ผ่าน -> exit 1
python src/registry.py rollback [VER]  # @champion ย้อนไปเวอร์ชันล่าสุดที่เคยผ่าน gate (หรือ VER)
```

ใน Docker ให้ขึ้นต้นด้วย `docker compose run --rm train` เช่น `docker compose run --rm train python src/registry.py status`

**Gate (Gating metric)** วัดตัวใหม่และตัวเดิมบน test ชุดเดียวกัน ต้องผ่านทุกข้อ:
- MAE ต่ำกว่า dummy (median)
- MAE ต่ำกว่า `@champion` ตัวเดิมอย่างน้อย 5% (ครั้งแรกที่ยังไม่มี champion ข้ามข้อนี้)
- P95 latency ของการทำนาย 1 order < 200 ms

API โหลด `@champion` ตอนเริ่มเท่านั้น หลัง promote หรือ rollback ให้ `docker compose restart api` (หรือใช้ `pipeline.py --deploy` ที่ทำให้อัตโนมัติ) `/health` และ `/predict` บอกเวอร์ชันที่ใช้อยู่

### สาธิต promote / reject / rollback

เริ่มจาก registry ว่าง (`docker compose down -v`):

```bash
docker compose up -d mlflow
CANDIDATES=dummy_median,linear_regression docker compose run --rm train   # v1 = linear "รุ่นเก่า" -> ผ่าน -> @champion
docker compose run --rm train      # v2 = hgb ดีกว่า v1 เกิน 5% -> ผ่าน -> @champion
docker compose run --rm train      # v3 = เทรนซ้ำข้อมูลเดิม ไม่ดีขึ้น 5% -> REJECTED (exit 1), API ยังใช้ v2
docker compose up -d api && curl localhost:8000/health          # version 2
docker compose run --rm train python src/registry.py rollback   # @champion v2 -> v1
docker compose restart api && curl localhost:8000/health        # version 1
```

PowerShell: ใช้ `$env:CANDIDATES = "dummy_median,linear_regression"; docker compose run --rm train` แล้ว `$env:CANDIDATES = ""` ก่อนรันบรรทัดถัดไป และใช้ `curl.exe` แทน `curl`
