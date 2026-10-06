# สินค้าจะมาถึงเมื่อไหร่: พยากรณ์ระยะเวลาจัดส่ง (Olist)

ระบบทำนายจำนวนวันตั้งแต่สั่งซื้อจนลูกค้าได้รับของ (`delivery_days`, Regression) เพื่อแสดง ETA ตอน checkout
ใช้ข้อมูล [Olist Brazilian E-commerce](https://kaggle.com/olistbr/brazilian-ecommerce) ~95,000 order

โมเดลปัจจุบัน (HistGradientBoosting) คลาดเคลื่อนเฉลี่ย **3.39 วัน** เทียบค่าประมาณเดิมของ Olist 10.79 วัน

```
ข้อมูลดิบ → prepare.py → Pandera → train (MLflow) → gate → @champion → FastAPI ใน Docker → ผู้ใช้
                        └── Prefect DAG คุมทั้งเส้น ──┘                       │
                                       monitor.py (Evidently) ◄── /metrics ─┘ → Slack
                                       GitHub Actions ตรวจโค้ด/ข้อมูล/โมเดลทุก PR
```

## สิ่งที่ต้องมี

- Docker Desktop (เปิดไว้)
- Python 3.11 (เช่น `conda create -n delivery-eta python=3.11`)

## เริ่มใช้งาน (คำสั่งเดียว)

รันจากโฟลเดอร์หลักของ repo:

```bash
pip install -r requirements.txt -r requirements-dag.txt -r requirements-monitor.txt
docker compose up -d mlflow && MLFLOW_TRACKING_URI=http://localhost:5050 python src/pipeline.py --deploy
```

PowerShell:

```powershell
pip install -r requirements.txt -r requirements-dag.txt -r requirements-monitor.txt
docker compose up -d mlflow; $env:MLFLOW_TRACKING_URI="http://localhost:5050"; python src/pipeline.py --deploy
```

ครั้งแรกใช้ ~3 นาทีหลังลง package (build image + เทรน) ทำงานตามลำดับ: เตรียมข้อมูลจากไฟล์ดิบ → ตรวจ schema → เทรน 4 โมเดล → gate → เปิด API ด้วยโมเดลที่ผ่าน

| Exit code | ความหมาย |
|---|---|
| 0 | สำเร็จ API ให้บริการโมเดลใหม่แล้ว |
| 2 | ข้อมูลไม่ผ่าน schema หยุดก่อนเทรน |
| 3 | gate ปฏิเสธโมเดลใหม่ API ใช้ตัวเดิม (ผลปกติเมื่อรันซ้ำด้วยข้อมูลเดิม) |

## ใช้งาน

| ที่อยู่ | คืออะไร |
|---|---|
| http://localhost:8000 | หน้าเว็บทดลองกรอก order |
| http://localhost:8000/docs | เอกสาร API |
| http://localhost:8000/health | สถานะและเวอร์ชันโมเดล |
| http://localhost:8000/metrics | P50/P95 latency และตัวนับคำขอ |
| http://localhost:5050 | MLflow UI (ผลการทดลอง และทะเบียนโมเดล) |

```bash
curl -X POST http://localhost:8000/predict -H "Content-Type: application/json" \
  -d '{"customer_state":"SP","seller_state":"SP","customer_lat":-23.5,"customer_lng":-46.6,"seller_lat":-23.6,"seller_lng":-46.7,"n_sellers":1,"n_items":2,"total_price":100.0,"total_freight":15.0,"total_weight_g":800.0,"estimated_delivery_days":10,"order_purchase_timestamp":"2018-05-01T10:00:00"}'
# {"predicted_delivery_days": 2.63, "model_version": "1"}
```

ข้อมูลไม่ผ่าน schema ได้ HTTP 422 และส่งแจ้งเตือน (Slack ถ้าตั้ง `SLACK_WEBHOOK_URL` ไม่ตั้งจะลง `logs/alerts.log`)

## คำสั่งที่ใช้บ่อย

```bash
python tests/check_cases.py --url http://localhost:8000          # test case ปกติ + ข้อมูลเสีย 6 ไฟล์
python loadtest/run.py --url http://localhost:8000               # วัด P50, P95, throughput
python src/pipeline.py --data demo_data/bad_orders.csv           # ข้อมูลเสีย: pipeline หยุดที่ validate (exit 2)

python src/monitor.py --current demo_data/normal_orders.csv      # exit 0  ไม่พบ drift
python src/monitor.py --current demo_data/drift_north.csv        # exit 2  Data Drift
python src/monitor.py --current demo_data/drift_blackfriday.csv  # exit 3  Concept Drift

python src/registry.py status                                    # ดูทุกเวอร์ชันของโมเดล
python src/registry.py rollback                                  # ย้อน @champion ไปเวอร์ชันก่อนหน้า แล้ว docker compose restart api
```

คำสั่ง `monitor.py` และ `registry.py` ต้องตั้ง `MLFLOW_TRACKING_URI=http://localhost:5050` ให้ชี้ server เดียวกับ API

**ใช้ Docker อย่างเดียว (ไม่ลง Python):** `docker compose up -d mlflow`, `docker compose run --rm train`, `docker compose up -d api` (เริ่มจาก CSV ที่ commit ไว้ ไม่ผ่าน `prepare.py`) ปิดทั้งหมดด้วย `docker compose down` (ใส่ `-v` ถ้าจะล้าง registry)

## เอกสาร

| เอกสาร | เนื้อหา |
|---|---|
| [docs/data.md](docs/data.md) | ข้อมูลดิบ, `prepare.py`, คอลัมน์, schema, การแบ่งข้อมูล, ข้อมูล demo |
| [docs/model.md](docs/model.md) | เทรน, ผลการทดลอง, MLflow tracking, registry, gate, rollback |
| [docs/pipeline.md](docs/pipeline.md) | Prefect DAG และ `--deploy` |
| [docs/serving.md](docs/serving.md) | API, metrics, logging, SLO, load test |
| [docs/monitoring.md](docs/monitoring.md) | Data/Concept Drift, เกณฑ์แจ้งเตือน, นโยบายเทรนใหม่, Slack |
| [docs/ci.md](docs/ci.md) | GitHub Actions 3 ด้าน |
| [docs/report.md](docs/report.md) | รายงานโครงงาน: โจทย์, เหตุผลที่เลือกเครื่องมือ, หลักฐานผลทดสอบ |

## เครื่องมือ

| หน้าที่ | เครื่องมือ |
|---|---|
| Version Control | Git + GitHub (branch + Pull Request) |
| Containerization | Docker + docker compose |
| Data Validation | Pandera (`src/schema.py`) |
| Experiment Tracking + Model Registry | MLflow (`src/train.py`, `src/registry.py`) |
| Pipeline Orchestration | Prefect (`src/pipeline.py`) |
| Model Serving | FastAPI + uvicorn (`src/api.py`) |
| Monitoring | Evidently + เขียนเอง (`src/monitor.py`) |
| CI/CD | GitHub Actions (`.github/workflows/ci.yml`) |

เหตุผลที่เลือกแต่ละตัวอยู่ใน [docs/report.md](docs/report.md#8-เหตุผลที่เลือกเครื่องมือ)

## โครงสร้าง repo

```text
src/                       โค้ดทั้งหมด (prepare, schema, features, train, registry, api, pipeline, monitor, alerts)
tests/                     test cases (good_/bad_*.json) และ check_cases.py
loadtest/                  load test
demo_data/                 ข้อมูลจำลอง: ปกติ, drift ภาคเหนือ, Black Friday, ข้อมูลเสีย
raw_data + Data prepair/   ข้อมูลดิบ Olist + notebook/สคริปต์ทำความสะอาดเดิม
cleaned_data/              CSV ที่ใช้เทรน (สร้างจาก src/prepare.py)
evidently/                 สคริปต์ทดลอง drift รอบแรกและ HTML report
docs/                      เอกสาร
team/                      เอกสารภายในทีม: โจทย์วิชา, แผนแบ่งงาน, to-do
```

โมเดลที่เทรนแล้วอยู่ใน MLflow registry (volume `mlflow-data`) ไม่ได้ commit ลง git
