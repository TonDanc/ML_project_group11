# Pipeline แบบ DAG (Prefect): `src/pipeline.py`

คำสั่งเดียวรันทั้งกระบวนการ ตั้งแต่ข้อมูลดิบจนถึง API ที่ให้บริการโมเดลใหม่

```
prepare_data ──► validate_data ──► train ──► gate ──► deploy (ถ้าใส่ --deploy)
 ข้อมูลดิบ → CSV     Pandera          MLflow     registry.py      สร้าง API container ใหม่
                    │                            promote          แล้วรอ /health ตอบ @champion
                    └─ ข้อมูลเสีย: หยุด exit 2      └─ gate ปฏิเสธ: exit 3 (API ใช้ตัวเดิม)
```

## วิธีรัน (จากโฟลเดอร์หลักของ repo)

```bash
pip install -r requirements.txt -r requirements-dag.txt

# คำสั่งเดียวจนถึงการให้บริการ (ต้องเปิด Docker)
docker compose up -d mlflow
MLFLOW_TRACKING_URI=http://localhost:5050 python src/pipeline.py --deploy

# แบบไม่ deploy (เทรนลง mlflow.db ในเครื่อง)
python src/pipeline.py
python src/pipeline.py --data demo_data/bad_orders.csv   # สาธิตข้อมูลเสีย: หยุดที่ validate, exit 2
```

PowerShell: `$env:MLFLOW_TRACKING_URI="http://localhost:5050"; python src/pipeline.py --deploy`

เทรนเร็วขึ้นตอนซ้อม: `CANDIDATES=dummy_median,hgb_default python src/pipeline.py`

ต้องตั้ง `MLFLOW_TRACKING_URI` ให้ชี้ server เดียวกับ API ไม่อย่างนั้นโมเดลจะไปอยู่ใน `mlflow.db` ในเครื่องที่ API มองไม่เห็น เปลี่ยน URL ของ API ได้ด้วย env `API_URL` (ค่าเริ่มต้น `http://localhost:8000`)

| Exit code | ความหมาย |
|---|---|
| 0 | ทุกขั้นสำเร็จ โมเดลใหม่เป็น `@champion` (และ API ใช้ตัวใหม่ ถ้าใส่ `--deploy`) |
| 2 | ข้อมูลไม่ผ่าน schema หยุดก่อนเทรน ไม่มี run ใหม่ใน MLflow |
| 3 | เทรนเสร็จแต่ gate ปฏิเสธ `@champion` ตัวเดิมยังใช้งานต่อ (ผลปกติ ไม่ใช่บั๊ก) |
| 1 | crash จริง หรือ deploy แล้ว API ไม่ตอบ `@champion` ภายใน 180 วินาที |

## แต่ละ task

| Task | เรียกอะไร | เทียบ TFX | ถ้าไม่ผ่าน |
|---|---|---|---|
| `prepare_data` | `prepare()` ใน `src/prepare.py` (ดู [data.md](data.md)) ข้ามถ้าไม่มีโฟลเดอร์ข้อมูลดิบ | ExampleGen | exception → exit 1 |
| `validate_data` | `load_splits(path)` จาก `train.py` (ใช้ `input_schema`) | ExampleValidator | `SchemaError` → exit 2 |
| `train` | `python src/train.py` ผ่าน `subprocess` | Trainer | task พัง → exit 1 |
| `gate` | `python src/registry.py promote` | Evaluator + Pusher ("blessing") | return code ≠ 0 → exit 3 |
| `deploy` | `docker compose up -d --force-recreate api` แล้วรอ `GET /health` ตอบเวอร์ชัน `@champion` | Pusher ไปถึง serving | `RuntimeError` → exit 1 |

**ทำไมเรียก `train` กับ `gate` ผ่าน `subprocess`:** โค้ดของสองไฟล์อยู่ใต้ `if __name__ == '__main__':` จึง import มาเรียกเป็นฟังก์ชันไม่ได้

**ทำไม gate ไม่โยน exception:** โมเดลใหม่ไม่ดีพอเป็นผลปกติของระบบ (blessing = false) task จึงคืน `True/False` ให้ flow ตัดสินใจ

**ทำไม deploy สร้าง container ใหม่:** API โหลด `@champion` ตอนเริ่มเท่านั้น และมี 8 workers ต่างคนต่างโหลด การสร้าง container ใหม่ทำให้ทุก worker ได้เวอร์ชันเดียวกัน ข้อแลกคือ API หยุดไม่กี่วินาที จึงเป็น opt-in (`--deploy`) และทำเฉพาะเมื่อ gate ผ่าน

**ทำไม validate ไม่มี retries:** ข้อมูลเสียลองใหม่กี่รอบก็เสียเหมือนเดิม

**เวอร์ชัน:** pin `prefect==3.4.25` เพราะ 3.5 ขึ้นไปต้องการ `fastapi>=0.139` ซึ่งชนกับ `fastapi==0.115.12` ของ API

## ดูกราฟ DAG ใน Prefect UI (ไม่บังคับ)

```bash
prefect server start          # http://127.0.0.1:4200
# อีก terminal:
prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api
python src/pipeline.py
```

แต่ละ task เป็นสีเขียว (สำเร็จ) หรือแดง (ล้ม) รันด้วย `bad_orders.csv` จะเห็น `validate_data` แดงและไม่มี `train`, `gate` ต่อ

![DAG รันสำเร็จครบทุก task](img/dag.png)

![DAG หยุดที่ validate_data เมื่อข้อมูลเสีย](img/dag-validate-red.png)

## ข้อจำกัด

- ข้อมูลดิบไม่อยู่ใน Docker image (`.dockerignore`) ถ้ารัน pipeline ใน container จะข้าม `prepare_data` แล้วใช้ CSV ที่ commit ไว้
- `--data` ใช้กับขั้น validate เท่านั้น `train.py` และ `registry.py` อ่าน `DATA_PATH` เสมอ จึงมีไว้สาธิต "ข้อมูลเสียแล้วระบบหยุด"
- `--deploy` ต้องรันบนเครื่องที่มี Docker และสั่งจากโฟลเดอร์หลักของ repo และไม่ build image ใหม่ ถ้าแก้โค้ด API ให้ `docker compose build` ก่อน
- ถ้าเคยตั้ง `PREFECT_API_URL` ไว้ ต้องเปิด `prefect server start` ก่อน ไม่อย่างนั้นจะล้มด้วย `Failed to reach API at http://127.0.0.1:4200/api/`
- ยังไม่มีตัวตั้งเวลา ต้องสั่งรันเอง หรือต่อจาก `monitor.py` (ดู [monitoring.md](monitoring.md))
