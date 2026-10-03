# Pipeline แบบ DAG (Prefect) — `src/pipeline.py`

ผู้รับผิดชอบ: Phonnatcha-kku (branch `dag`)

## สรุปสั้น

คำสั่งเดียวรันทั้งกระบวนการ: **ตรวจข้อมูล → เทรน → ด่านอนุมัติ (gate) → smoke test**

```
validate_data  ──►  train  ──►  gate  ──►  smoke_test (ถ้าตั้ง API_URL)
 (Pandera)         (MLflow)     (registry.py promote → @champion)   (GET /health)
     │                            │
     └─ ข้อมูลเสีย: หยุด, exit 2      └─ โมเดลไม่ผ่านเกณฑ์: exit 3
```

## วิธีรัน (จากโฟลเดอร์หลักของ repo)

```bash
pip install -r requirements.txt -r requirements-dag.txt

python src/pipeline.py                                  # ข้อมูลปกติ -> exit 0 (หรือ 3 ถ้า gate ปฏิเสธ)
python src/pipeline.py --data demo_data/bad_orders.csv  # ข้อมูลเสีย -> หยุดที่ validate, exit 2
API_URL=http://localhost:8000 python src/pipeline.py    # หลัง gate ผ่าน เช็คว่า API ใช้เวอร์ชันไหน
```

เทรนเร็วขึ้นตอนซ้อม: `CANDIDATES=dummy_median,hgb_default python src/pipeline.py`
(PowerShell: `$env:CANDIDATES="dummy_median,hgb_default"; python src/pipeline.py`)

| Exit code | ความหมาย |
|---|---|
| 0 | ทุกขั้นสำเร็จ โมเดลใหม่ได้เป็น `@champion` |
| 2 | ข้อมูลไม่ผ่าน schema หยุดก่อนเทรน (ไม่มี run ใหม่ใน MLflow) |
| 3 | เทรนเสร็จแต่ gate ปฏิเสธโมเดล `@champion` ตัวเดิมยังใช้งานต่อ (ไม่ใช่บั๊ก) |
| 1 | crash จริง (เช่น `train.py` พัง) |

## แต่ละ task ทำอะไร

| Task | เรียกอะไร | เทียบ TFX (Lecture 11) | ถ้าไม่ผ่าน |
|---|---|---|---|
| `validate_data` | `load_splits(path)` จาก `train.py` (ข้างในใช้ `input_schema` ของ Pandera) | ExampleValidator | Pandera โยน `SchemaError` → flow คืน 2 |
| `train` | `python src/train.py` ผ่าน `subprocess` | Trainer | `check=True` ทำให้ task พัง → exit 1 |
| `gate` | `python src/registry.py promote` | Evaluator + Pusher ("blessing") | return code ≠ 0 → flow คืน 3 |
| `smoke_test` | `GET {API_URL}/health` เทียบ `version` กับ `@champion` (รันเฉพาะเมื่อ gate ผ่านและตั้ง env `API_URL`) | ตรวจหลัง deploy | พิมพ์ `WARN` เท่านั้น ไม่เปลี่ยน exit code |

**ทำไม `train` กับ `gate` เรียกผ่าน `subprocess`:** โค้ดใน `train.py` และ `registry.py` อยู่ใต้ `if __name__ == '__main__':` จึง import มาเรียกเป็นฟังก์ชันไม่ได้ การรันเป็นโปรแกรมแยกทำให้ไม่ต้องแก้ไฟล์ของคนอื่นเลย

**ทำไม gate ไม่ใช่ exception:** การที่โมเดลใหม่ไม่ดีพอเป็นผลลัพธ์ปกติของระบบ (เหมือน blessing = false ในสไลด์) task `gate` จึงคืนค่า `True/False` แล้ว flow ตัดสินใจเอง

**ทำไม smoke_test ไม่สั่ง restart API เอง:** API โหลด `@champion` ตอนเริ่มเท่านั้น ถ้า gate เพิ่งเลื่อนเวอร์ชัน API จะยังใช้ตัวเก่า task นี้จึงพิมพ์เตือนให้ `docker compose restart api` ตาม GUIDE (ไม่ restart เอง เพราะ pipeline ไม่ควรไปหยุด service ที่ลูกค้ากำลังใช้) และถ้าเรียก API ไม่ได้ก็แค่เตือน เพราะ API เป็นคนละระบบกับการเทรน

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

- **DAG เริ่มจาก `cleaned_data/feature extraction/shipping_distance_duration.csv` ไม่ใช่ข้อมูลดิบ** สคริปต์ใน `raw_data + Data prepair/` ใช้ path `archive/clean/...` ที่ไม่ตรงกับ repo และไฟล์ดิบไม่อยู่ใน Docker image
- **`--data` ใช้กับขั้น validate เท่านั้น** `train.py` และ `registry.py` อ่าน `DATA_PATH` เสมอ (แก้ไม่ได้โดยไม่แตะไฟล์ของ tharathep) ดังนั้น `--data` มีไว้สาธิต "ข้อมูลเสียแล้วระบบหยุด"
- หลัง gate ผ่านต้อง restart API เองเพื่อโหลด `@champion` ตัวใหม่ (`smoke_test` แค่เตือน)
- ถ้าเคยรัน `prefect config set PREFECT_API_URL=...` ไว้ ต้องเปิด `prefect server start` ก่อนรัน pipeline ไม่อย่างนั้นจะล้มด้วย `Failed to reach API at http://127.0.0.1:4200/api/`

## ผลทดสอบ (2 ต.ค. 2569, `CANDIDATES=dummy_median,hgb_default`, MLflow sqlite เปล่า)

| คำสั่ง | ผล | Exit |
|---|---|---|
| `python src/pipeline.py --data demo_data/bad_orders.csv` | `validate_data` ล้ม (n_items=`abc`, timestamp=`not-a-date`) ไม่เทรน | 2 |
| `python src/pipeline.py` (รอบแรก) | hgb_default test MAE 3.389 ชนะ dummy 5.057 → PROMOTED v1 | 0 |
| `python src/pipeline.py` (รอบสอง) | v2 MAE 3.389 ไม่ดีกว่า v1 ถึง 5% → REJECTED | 3 |

### ผลทดสอบ `smoke_test` (4 ต.ค. 2569, MLflow sqlite เปล่า, API ใน Docker ใช้ v1)

| คำสั่ง | ผล | Exit |
|---|---|---|
| `CANDIDATES=dummy_median,linear_regression API_URL=http://localhost:9999 python src/pipeline.py` | PROMOTED v1, `WARN: smoke test เรียก http://localhost:9999/health ไม่ได้` | 0 |
| `CANDIDATES=hgb_default API_URL=http://localhost:8000 python src/pipeline.py` | PROMOTED v2, `WARN: API ยังใช้ v1 แต่ @champion คือ v2 -> restart API` | 0 |
| API ใช้ v1 และ `@champion` คือ v1 | พิมพ์ `/health` อย่างเดียว ไม่มี WARN | - |
| `API_URL=http://localhost:8000 python src/pipeline.py --data demo_data/bad_orders.csv` | หยุดที่ validate ไม่ถึง smoke_test | 2 |

## ไฟล์ที่เพิ่ม (ไม่ได้แก้ไฟล์เดิม)

- `src/pipeline.py` — Prefect flow 4 task (smoke_test ไม่บังคับ)
- `requirements-dag.txt` — `prefect==3.4.25`
- `docs/pipeline.md` — ไฟล์นี้
