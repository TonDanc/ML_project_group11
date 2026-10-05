# Pipeline แบบ DAG (Prefect) — `src/pipeline.py`

ผู้รับผิดชอบ: Phonnatcha-kku (branch `dag`)

## สรุปสั้น

คำสั่งเดียวรันทั้งกระบวนการ: **ข้อมูลดิบ → เตรียมข้อมูล → ตรวจข้อมูล → เทรน → ด่านอนุมัติ (gate) → ให้บริการ (deploy)**

```
prepare_data  ──►  validate_data  ──►  train  ──►  gate  ──►  deploy (ถ้าใส่ --deploy)
 (raw 8 ไฟล์ → CSV)  (Pandera)         (MLflow)     (registry.py promote → @champion)   (สร้าง API container ใหม่ + รอ /health)
     │                            │
     └─ ข้อมูลเสีย: หยุด, exit 2      └─ โมเดลไม่ผ่านเกณฑ์: exit 3
```

## วิธีรัน (จากโฟลเดอร์หลักของ repo)

```bash
pip install -r requirements.txt -r requirements-dag.txt

python src/pipeline.py                                  # ข้อมูลปกติ -> exit 0 (หรือ 3 ถ้า gate ปฏิเสธ)
python src/pipeline.py --data demo_data/bad_orders.csv  # ข้อมูลเสีย -> หยุดที่ validate, exit 2
```

### คำสั่งเดียวจนถึงการให้บริการ

```bash
docker compose up -d mlflow     # ครั้งแรกครั้งเดียว (MLflow server ที่ API ใช้)
MLFLOW_TRACKING_URI=http://localhost:5050 python src/pipeline.py --deploy
```

PowerShell: `$env:MLFLOW_TRACKING_URI="http://localhost:5050"; python src/pipeline.py --deploy`

หลัง gate ผ่าน task `deploy` จะสั่ง `docker compose up -d --force-recreate api` ให้ API โหลด `@champion` ตัวใหม่
แล้วรอจน `GET /health` ตอบ `status=ok` และ `version` ตรงกับ `@champion` (สูงสุด 180 วินาที) ถ้า gate ไม่ผ่านจะไม่แตะ API เลย
ต้องตั้ง `MLFLOW_TRACKING_URI` ให้ชี้ server เดียวกับ API ไม่อย่างนั้นโมเดลจะไปอยู่ใน `mlflow.db` ในเครื่องที่ API มองไม่เห็น
เปลี่ยน URL ของ API ได้ด้วย env `API_URL` (ค่าเริ่มต้น `http://localhost:8000`)

เทรนเร็วขึ้นตอนซ้อม: `CANDIDATES=dummy_median,hgb_default python src/pipeline.py`
(PowerShell: `$env:CANDIDATES="dummy_median,hgb_default"; python src/pipeline.py`)

| Exit code | ความหมาย |
|---|---|
| 0 | ทุกขั้นสำเร็จ โมเดลใหม่ได้เป็น `@champion` |
| 2 | ข้อมูลไม่ผ่าน schema หยุดก่อนเทรน (ไม่มี run ใหม่ใน MLflow) |
| 3 | เทรนเสร็จแต่ gate ปฏิเสธโมเดล `@champion` ตัวเดิมยังใช้งานต่อ (ไม่ใช่บั๊ก) |
| 1 | crash จริง (เช่น `train.py` พัง) หรือ deploy แล้ว API ไม่ตอบ `@champion` ภายในเวลา |

## แต่ละ task ทำอะไร

| Task | เรียกอะไร | เทียบ TFX (Lecture 11) | ถ้าไม่ผ่าน |
|---|---|---|---|
| `prepare_data` | `prepare()` ใน `src/prepare.py`: ข้อมูลดิบ 8 ไฟล์ใน `raw_data + Data prepair/raw data/` → `shipping_distance_duration.csv` (ข้ามถ้าไม่มีโฟลเดอร์ข้อมูลดิบ) | ExampleGen | exception → exit 1 |
| `validate_data` | `load_splits(path)` จาก `train.py` (ข้างในใช้ `input_schema` ของ Pandera) | ExampleValidator | Pandera โยน `SchemaError` → flow คืน 2 |
| `train` | `python src/train.py` ผ่าน `subprocess` | Trainer | `check=True` ทำให้ task พัง → exit 1 |
| `gate` | `python src/registry.py promote` | Evaluator + Pusher ("blessing") | return code ≠ 0 → flow คืน 3 |
| `deploy` | `docker compose up -d --force-recreate api` แล้วรอ `GET /health` ตอบ `@champion` (รันเฉพาะเมื่อ gate ผ่านและใส่ `--deploy`) | Pusher ไปถึง serving | โยน `RuntimeError` → exit 1 |

**ทำไม `train` กับ `gate` เรียกผ่าน `subprocess`:** โค้ดใน `train.py` และ `registry.py` อยู่ใต้ `if __name__ == '__main__':` จึง import มาเรียกเป็นฟังก์ชันไม่ได้ การรันเป็นโปรแกรมแยกทำให้ไม่ต้องแก้ไฟล์ของคนอื่นเลย

**ทำไม gate ไม่ใช่ exception:** การที่โมเดลใหม่ไม่ดีพอเป็นผลลัพธ์ปกติของระบบ (เหมือน blessing = false ในสไลด์) task `gate` จึงคืนค่า `True/False` แล้ว flow ตัดสินใจเอง

**ทำไม deploy สร้าง container ใหม่:** API โหลด `@champion` ตอนเริ่มเท่านั้น (8 workers ต่างคนต่างโหลด) การสร้าง container ใหม่ทำให้ทุก worker ได้เวอร์ชันเดียวกันโดยไม่ต้องแก้ `api.py` ข้อแลกคือ API หยุดให้บริการไม่กี่วินาทีระหว่างเปิดใหม่ จึงให้เป็น opt-in ผ่าน `--deploy` และทำเฉพาะเมื่อ gate ผ่านแล้ว

**ทำไม validate ไม่มี retries:** ข้อมูลเสียลองใหม่กี่รอบก็เสียเหมือนเดิม (เหตุผลเดียวกับ `AirflowFailException` ใน airflow_lab)

## แนวคิดจาก Lecture 11 ที่ใช้

- **Orchestrator = กาว** ที่คุมลำดับงาน: ใน Prefect ลำดับการเรียกฟังก์ชันใน `@flow` คือเส้นของ DAG ขั้นถัดไปเริ่มได้เมื่อขั้นก่อนสำเร็จเท่านั้น
- **DAG (Directed Acyclic Graph):** ไหลทางเดียว validate → train → gate ไม่มีวงย้อนกลับ
- **Data Definition (Garbage In, Garbage Out):** ตรวจข้อมูลก่อนเทรนเสมอ schema ใน `schema.py` คงที่ ไม่สร้างใหม่ทุกรอบ
- **Baseline + Blessing:** gate เทียบกับ baseline 2 ตัว คือ dummy (ทายค่ามัธยฐาน) และ `@champion` ตัวปัจจุบัน (ต้องดีกว่า 5%) พร้อม P95 < 200 ms ผ่านแล้วจึง "push" เป็น `@champion`

## ทำไมเลือก Prefect (ไม่ใช่ Airflow / Dagster)

| | Prefect | Airflow (ใน lab) | Dagster |
|---|---|---|---|
| ติดตั้ง | `pip install` ตัวเดียว | ต้อง Docker + scheduler + DB | `pip install` แต่ต้องเรียนแนวคิด asset/op เพิ่ม |
| รันในเครื่อง | `python src/pipeline.py` ได้เลย (มี server ชั่วคราวให้อัตโนมัติ) | ต้องเปิด webserver/scheduler | ต้องใช้ `dagster dev` หรือเขียนโค้ดสั่งรันเอง |
| โค้ด | ฟังก์ชัน Python ธรรมดา + `@flow`/`@task` | `@dag`/`@task` คล้ายกัน | `@op`/`@job` หรือ `@asset` |

`@flow`/`@task` ของ Prefect หน้าตาเหมือน TaskFlow API (`@dag`/`@task`) ใน airflow_lab แทบทุกอย่าง จึงอ่านเทียบกันได้ตรงๆ

**เวอร์ชัน:** pin `prefect==3.4.25` เพราะ prefect 3.5 ขึ้นไปต้องการ `fastapi>=0.139` ซึ่งชนกับ `fastapi==0.115.12` ที่ API ใช้

## ดูกราฟ DAG ใน Prefect UI (ไม่บังคับ)

```bash
prefect server start          # เปิด http://127.0.0.1:4200
# อีก terminal:
prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api
python src/pipeline.py
```

ในหน้า Flow Runs จะเห็นแต่ละ task เป็นสีเขียว (สำเร็จ) / แดง (ล้ม) เช่นรันด้วย `bad_orders.csv` จะเห็น `validate_data` เป็นสีแดงและไม่มี `train`, `gate` ต่อ

## ข้อจำกัดที่ต้องรู้

- ข้อมูลดิบไม่อยู่ใน Docker image (`.dockerignore`) ถ้ารัน pipeline ใน container จะข้าม `prepare_data` แล้วใช้ CSV ที่ commit ไว้
- **`--data` ใช้กับขั้น validate เท่านั้น** `train.py` และ `registry.py` อ่าน `DATA_PATH` เสมอ (แก้ไม่ได้โดยไม่แตะไฟล์ของ tharathep) ดังนั้น `--data` มีไว้สาธิต "ข้อมูลเสียแล้วระบบหยุด"
- `--deploy` ต้องรันบนเครื่องที่มี Docker และ stack ของ `docker-compose.yml` (สั่ง `docker compose` จากโฟลเดอร์หลักของ repo) ระหว่างสร้าง API ใหม่จะหยุดให้บริการไม่กี่วินาที
- ถ้าเคยรัน `prefect config set PREFECT_API_URL=...` ไว้ ต้องเปิด `prefect server start` ก่อนรัน pipeline ไม่อย่างนั้นจะล้มด้วย `Failed to reach API at http://127.0.0.1:4200/api/`

## ผลทดสอบ (2 ต.ค. 2569, `CANDIDATES=dummy_median,hgb_default`, MLflow sqlite เปล่า)

| คำสั่ง | ผล | Exit |
|---|---|---|
| `python src/pipeline.py --data demo_data/bad_orders.csv` | `validate_data` ล้ม (n_items=`abc`, timestamp=`not-a-date`) ไม่เทรน | 2 |
| `python src/pipeline.py` (รอบแรก) | hgb_default test MAE 3.389 ชนะ dummy 5.057 → PROMOTED v1 | 0 |
| `python src/pipeline.py` (รอบสอง) | v2 MAE 3.389 ไม่ดีกว่า v1 ถึง 5% → REJECTED | 3 |

### ผลทดสอบ `--deploy` (6 ต.ค. 2569, docker compose stack แยกที่ registry เปล่า, API เริ่มที่ `unavailable`)

| คำสั่ง | ผล | Exit |
|---|---|---|
| `CANDIDATES=dummy_median,linear_regression python src/pipeline.py --deploy` | PROMOTED v1, API ถูกสร้างใหม่ `/health` = `{'status': 'ok', 'version': '1'}` | 0 |
| `CANDIDATES=hgb_default python src/pipeline.py --deploy` | PROMOTED v2 (was v1), API ตอบ `version: '2'` | 0 |
| `python src/pipeline.py --deploy --data demo_data/bad_orders.csv` | หยุดที่ validate ไม่เทรน ไม่แตะ API | 2 |
| `CANDIDATES=hgb_default python src/pipeline.py --deploy` (รอบซ้ำ) | REJECTED ไม่ดีกว่า v2 ถึง 5% ไม่แตะ API (ยังตอบ v2) | 3 |

## `src/prepare.py` — ข้อมูลดิบ → CSV ที่ใช้เทรน

เดิมขั้นนี้ทำมือใน notebook และสคริปต์ที่ใช้ path `archive/clean/...` ซึ่งไม่ตรงกับ repo และไม่มีสคริปต์ที่สร้าง `order_items_full_merged.csv` เลย
`prepare.py` รวมทุกขั้นให้รันต่อกันได้ โดยไม่แก้ไฟล์เดิม:

| ขั้น | ที่มาของ logic |
|---|---|
| `clean_orders()` | `clean_loma(for order).ipynb` cell 18–26 (1 แถวต่อ order ที่มีรีวิวและส่งถึงแล้ว + `delivery_days`) |
| `clean_geolocation()`, `clean_products()` | `eda_explore_for_cust_geo_prod_seller_clean.ipynb` (ตัดพิกัดนอกบราซิล/ห่าง median ของ zip > 100 กม., เติมน้ำหนักด้วย median) |
| `item_level()` | แทน `order_items_full_merged.csv` ใช้ `aggregate_geolocation()` ของ `merge_all.py` |
| `build_shipping_dataset()` | import จาก `compute_shipping_distance.py` ตรงๆ |

**ตรวจว่าตรงกับไฟล์เดิม (6 ต.ค. 2569):** 95,824 order × 21 คอลัมน์ ไม่มีพิกัด 503 order ทุกค่าตรงกัน (ต่างกันแค่ทศนิยมหลักที่ 15 จากการปัดเศษ median)
แบ่ง train/val/test ได้ order ชุดเดียวกันทุกตัว (66,724 / 14,298 / 14,299) เทรน `hgb_default` ได้ test MAE 3.389 เท่าเดิม รันซ้ำได้ไฟล์เหมือนเดิมทุก byte
CSV ที่ commit ไว้จึงเปลี่ยนเป็นผลของ `prepare.py` (`data_md5` ใน MLflow เปลี่ยนจาก run ก่อนหน้า แต่ข้อมูลเหมือนเดิม)

```bash
python src/prepare.py                       # เขียน cleaned_data/feature extraction/shipping_distance_duration.csv (ประมาณ 40 วินาที)
python src/prepare.py --out /tmp/check.csv  # เขียนที่อื่นเพื่อเทียบ
```

### ผลทดสอบ DAG เต็ม (6 ต.ค. 2569, stack แยกที่ registry เปล่า, `CANDIDATES=dummy_median,hgb_default`)

| คำสั่ง | ผล | Exit |
|---|---|---|
| `python src/pipeline.py --deploy` | prepare_data → validate_data → train → gate (PROMOTED v1, MAE 3.389) → deploy (API ตอบ v1) ครบ 5 task | 0 |
| `python src/pipeline.py --deploy --data demo_data/bad_orders.csv` | prepare_data ผ่าน, validate_data ล้ม (`n_items=abc`, `not-a-date`) ไม่เทรน | 2 |

## ไฟล์ที่เพิ่ม (ไม่ได้แก้ไฟล์เดิม)

- `src/pipeline.py` — Prefect flow 5 task (deploy ไม่บังคับ ใช้ `--deploy`)
- `src/prepare.py` — ข้อมูลดิบ → CSV ที่ใช้เทรน
- `requirements-dag.txt` — `prefect==3.4.25`
- `docs/pipeline.md` — ไฟล์นี้
