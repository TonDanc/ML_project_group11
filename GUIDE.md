# GUIDE — แบ่งงานโครงงาน "สินค้าจะมาถึงเมื่อไหร่" (CP413008)

เอกสารนี้คือแผนทำงานของกลุ่ม อ่านส่วน 0 ถึง 3 ทุกคน แล้วข้ามไปอ่านส่วนของตัวเอง (ส่วน 4)

- **ส่งงาน:** อา. 4 ต.ค. 2569 เย็น (กำหนดจริงคือ จ. 5 ต.ค. 23:59 ใช้ จ. 5 เป็นวันสำรองเท่านั้น)
- **นำเสนอ:** จ. 12 ต.ค. 2569 08:30 (12 นาที + ถามตอบ 3 นาที)
- **ตอนนี้ main มีอะไรแล้ว:** Git/PR, Pandera schema, train + MLflow tracking, registry + gate + rollback, FastAPI, Dockerfile, docker-compose
- **ที่ยังขาด (คือสิ่งที่แบ่งในเอกสารนี้):** Monitoring/drift, DAG, CI/CD, `/metrics` + load test, Slack alert, test case, รายงาน + แผนภาพ

---

## 0. กฎเหล็ก 6 ข้อเพื่อไม่ให้ชนกัน

1. **1 คน = 1 branch = ไฟล์ของตัวเองเท่านั้น** ดูตารางความเป็นเจ้าของไฟล์ในส่วน 1 ห้ามแก้ไฟล์ที่เป็นของคนอื่น ถ้าจำเป็นให้บอกเจ้าของไฟล์
2. **ไฟล์ที่ทุกคนอยากแก้แต่ห้ามแก้** (`README.md`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `.gitignore`, `train.py`, `registry.py`, `features.py`, `schema.py`) เป็นของ **tharathep-kku คนเดียว** ถ้าต้องการอะไรให้ส่งข้อความหา แล้ว tharathep เพิ่มให้
   - ต้องการ library เพิ่ม: ใส่ในไฟล์ `requirements-<งานของคุณ>.txt` ของตัวเอง ไม่แตะ `requirements.txt`
   - ต้องการเขียนคำอธิบาย: เขียนใน `docs/<งานของคุณ>.md` ไม่แตะ `README.md` (tharathep จะ link ให้)
3. **ห้าม push ตรงเข้า `main`** ทุกอย่างผ่าน PR และต้องมีคนตรวจอย่างน้อย 1 คน (ตารางผู้ตรวจในส่วน 2)
4. **ก่อนเปิด PR ทุกครั้ง** รัน `git pull origin main` เข้า branch ตัวเอง แล้วรันเช็คในหัวข้อ "ตรวจก่อนเปิด PR" ของตัวเอง
5. **ติดต่อกันผ่านสัญญาเชื่อมต่อ (ส่วน 3) เท่านั้น** ชื่อฟังก์ชัน, ชื่อคีย์ JSON, exit code ต้องตรงตามนั้น ถ้าอยากเปลี่ยนต้องแจ้งทั้งกลุ่มก่อน
6. **ไม่ commit ความลับ:** Slack webhook URL ห้ามอยู่ใน repo ใช้ environment variable `SLACK_WEBHOOK_URL` เท่านั้น

### Git ขั้นต่ำที่ต้องใช้

```bash
git checkout main && git pull origin main
git checkout -b <ชื่อ-branch>          # ชื่อตามส่วน 1
# ... ทำงาน ... 
git add <เฉพาะไฟล์ของตัวเอง>           # อย่าใช้ git add . ดูให้ชัวร์ด้วย git status
git commit -m "ข้อความบอกว่าทำอะไร"
git push -u origin <ชื่อ-branch>
# เปิด PR บน GitHub: base = main, compare = branch ของเรา
```

ถ้า main เปลี่ยนระหว่างทำ: `git pull origin main` เข้า branch ตัวเอง (ไม่ควรเกิด conflict ถ้าแก้แต่ไฟล์ของตัวเอง)

---

## 1. ความเป็นเจ้าของไฟล์ (ใครแก้ไฟล์ไหนได้)

| คน | Branch | ไฟล์/โฟลเดอร์ที่เป็นเจ้าของ (สร้างใหม่ทั้งหมด ยกเว้นที่ระบุ) |
|---|---|---|
| **tharathep-kku** | `scaffold`, `integration` | `README.md`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `.gitignore`, `.dockerignore`, `src/train.py`, `src/registry.py`, `src/features.py`, `src/schema.py`, `src/test_schema.py`, `src/index.html`, `src/alerts.py` (สร้าง stub เท่านั้น) |
| **manatsanun** | `test-cases`, `serving-metrics` | `src/api.py` (ของเดิม), `tests/` , `loadtest/`, `docs/serving-metrics.md` |
| **thirawatv-sketch** | `ci`, `slack-alert` | `.github/workflows/`, `requirements-dev.txt`, `src/alerts.py` (เติมเนื้อหาต่อจาก stub), `docs/ci.md`, `docs/slack-alert.md` |
| **keerati-chawong** | `monitoring` | `src/monitor.py`, `requirements-monitor.txt`, `docs/monitoring.md` |
| **Phonnatcha-kku** | `dag` | `src/pipeline.py`, `requirements-dag.txt`, `docs/pipeline.md` |
| **TonDanc** | `report-demo` | `demo_data/`, `docs/architecture.md`, `docs/report.md`, `docs/demo-script.md`, `docs/img/` |

**ไฟล์ที่มีสองคนต้องแตะ (จุดเสี่ยงชน) และวิธีแก้:**

| ไฟล์ | ปัญหา | วิธีแก้ |
|---|---|---|
| `src/alerts.py` | manatsanun ต้องเรียก, thirawatv-sketch ต้องเขียนเนื้อหา | tharathep สร้าง stub ก่อนใน PR `scaffold` (ส่วน 4.1) manatsanun แค่ `import` ใน `api.py`, thirawatv-sketch เติมเนื้อหาในไฟล์ alerts.py เท่านั้น |
| `docker-compose.yml` | api ต้องได้ `SLACK_WEBHOOK_URL` | tharathep เพิ่มบรรทัดนี้ให้ใน `scaffold` |
| `requirements*.txt` | ทุกคนอยากเพิ่ม lib | แยกไฟล์ตามงาน ดูกฎข้อ 2 |
| `tests/` | CI ต้องเรียกสคริปต์ของ manatsanun | merge `test-cases` ก่อน แล้วค่อย merge `ci` (ลำดับในส่วน 2) |
| ข้อมูลจำลอง drift | keerati ต้องใช้ไฟล์ที่ TonDanc ทำ | สัญญาเชื่อมต่อข้อ C ในส่วน 3 และ keerati ไม่ต้องรอ (ใช้ val เป็นตัวแทนก่อน) |

---

## 2. ลำดับ merge และไทม์ไลน์

### ลำดับ merge เข้า `main` (ต้องเรียงตามนี้)

```
1. scaffold            (tharathep)       <- ต้องเสร็จก่อนใคร  คืนนี้ 2 ต.ค.
2. test-cases          (manatsanun)      <- เล็ก  เสร็จก่อนที่ ci จะ merge
3. serving-metrics     (manatsanun)      <- แก้ api.py  merge หลัง scaffold
   slack-alert         (thirawatv)       <- แก้ alerts.py อย่างเดียว  merge เมื่อไหร่ก็ได้หลัง scaffold
   monitoring          (keerati)         <- ไฟล์ใหม่ล้วน  merge เมื่อไหร่ก็ได้หลัง scaffold
   dag                 (Phonnatcha)      <- ไฟล์ใหม่ล้วน  merge เมื่อไหร่ก็ได้หลัง scaffold
   report-demo         (TonDanc)         <- ไฟล์ใหม่ล้วน  merge เมื่อไหร่ก็ได้หลัง scaffold
4. ci                  (thirawatv)       <- merge หลัง test-cases (ต้องเรียก tests/check_cases.py)
5. integration         (tharathep)       <- สุดท้าย  อัปเดต README, link docs, ซ้อมรันทั้งระบบ
```

เพราะแต่ละคนแก้ไฟล์ของตัวเอง ข้อ 3 ที่เขียนว่า "merge เมื่อไหร่ก็ได้" ไม่ชนกันไม่ว่าจะลำดับไหน

### ผู้ตรวจ PR

| PR ของ | ผู้ตรวจคนที่ 1 | ผู้ตรวจคนที่ 2 (ถ้ามีเวลา) |
|---|---|---|
| manatsanun | tharathep-kku | thirawatv-sketch |
| thirawatv-sketch | tharathep-kku | manatsanun |
| keerati-chawong | tharathep-kku | TonDanc |
| Phonnatcha-kku | tharathep-kku | keerati-chawong |
| TonDanc | tharathep-kku | Phonnatcha-kku |
| tharathep-kku | manatsanun | Phonnatcha-kku |

ผู้ตรวจต้องรันคำสั่งตรวจของ PR นั้นจริง ไม่ใช่แค่ดูโค้ด

### ไทม์ไลน์ 3 วัน

| วัน | เป้าหมาย |
|---|---|
| **ศ. 2 ต.ค. (วันนี้)** | tharathep merge `scaffold` ภายในคืนนี้ ทุกคนแตก branch และ push อย่างน้อย 1 commit ก่อนนอน manatsanun merge `test-cases` |
| **ส. 3 ต.ค.** | ทุก PR เปิดให้ครบภายในเย็น `serving-metrics`, `slack-alert` merge ก่อน |
| **อา. 4 ต.ค.** | แก้ตามรีวิว, merge ที่เหลือ, รายงานครบ, tharathep ซ้อมรันทั้งระบบจากเครื่องเปล่า **ส่งงานเย็นวันนี้** |
| **จ. 5 ต.ค.** | สำรองเท่านั้น ถ้ามีบั๊กค่อยแก้ ห้ามเพิ่มฟีเจอร์ |

หยุดเพิ่มฟีเจอร์ตอน **อา. 4 ต.ค. บ่าย** ถ้างานไม่ทัน ให้ลดเป็นเวอร์ชันง่ายตามหัวข้อ "ถ้าไม่ทัน" ของแต่ละคน

---

## 3. สัญญาเชื่อมต่อระหว่างงาน (Contracts)

ทุกงานต้องทำตามนี้เพื่อให้ต่อกันได้ ถ้าจะเปลี่ยนต้องแจ้งทั้งกลุ่ม

### A. `src/alerts.py` (stub โดย tharathep, เนื้อหาโดย thirawatv-sketch)

```python
def send_alert(title: str, detail: str = '') -> None: ...
def notify_validation_failure(detail: str, payload: dict | None = None) -> None: ...
```

- **ห้ามโยน exception ออกมาเด็ดขาด** (API ต้องไม่ล่มเพราะ Slack ล่ม)
- ใช้ env `SLACK_WEBHOOK_URL` ถ้าไม่ตั้ง ให้พิมพ์ `[ALERT] ...` ลง stdout และเขียนต่อท้าย `logs/alerts.log` แล้วจบ
- ผู้เรียก: `api.py` (manatsanun) เรียก `notify_validation_failure`, `monitor.py` (keerati) เรียก `send_alert`

### B. `/metrics` และ `/health` ของ API (manatsanun)

`GET /metrics` ตอบ JSON ดังนี้ (ชื่อคีย์ตายตัว):

```json
{
  "requests_total": 120,
  "errors_total": 3,
  "rejected_total": 2,
  "latency_ms": {"p50": 8.1, "p95": 21.4, "count": 120},
  "model_version": "2",
  "uptime_s": 345.2
}
```

`/health` ยังเป็นของเดิม (`status`, `model`, `version`) ห้ามเปลี่ยน

### C. ข้อมูลจำลอง drift (TonDanc สร้าง, keerati และ Phonnatcha ใช้)

ไฟล์ใน `demo_data/` คอลัมน์เหมือน `shipping_distance_duration.csv` (มี `delivery_days` ด้วย):

| ไฟล์ | เนื้อหา | ใช้โดย |
|---|---|---|
| `normal_orders.csv` | สุ่ม 500 แถวจาก test split | monitor, demo |
| `drift_north.csv` | แถวที่ `customer_state` ใน `AC, AP, AM, PA, RO, RR, TO` (ภาคเหนือ) | monitor (Data Drift) |
| `drift_blackfriday.csv` | แถวที่ `order_purchase_timestamp` ระหว่าง 2017-11-20 ถึง 2017-11-27 | monitor (Concept Drift) |
| `bad_orders.csv` | 50 แถวปกติ แต่ใส่ค่าเสียบางแถว (น้ำหนักติดลบ, `customer_state='XX'`, lat=40) | pipeline (demo หยุดที่ validate) |

สคริปต์สร้างอยู่ที่ `demo_data/make_demo_data.py` (รันจากโฟลเดอร์หลัก) ไฟล์ผลลัพธ์ต้องเล็ก (< 2 MB ต่อไฟล์)

### D. Exit code ของ `monitor.py` (keerati) และ `pipeline.py` (Phonnatcha)

| คำสั่ง | 0 | 2 | 3 |
|---|---|---|---|
| `python src/monitor.py --current <csv>` | ไม่พบ drift | พบ **Data Drift** | พบ **Concept Drift** (ถ้ามีทั้งสองให้คืน 3) |
| `python src/pipeline.py [--data <csv>]` | ทุกขั้นสำเร็จ | validate ไม่ผ่าน (หยุด) | gate ปฏิเสธโมเดล |

เกณฑ์ drift (ตายตัว ต้องเหมือนกันทั้งรายงานและโค้ด):
- **Data Drift:** KS test หรือ PSI ของ `total_weight_g` หรือ `distance_km` เทียบกับ train: PSI > 0.2 หรือ KS p-value < 0.01
- **Concept Drift:** MAE ของ `@champion` บนข้อมูลช่วงนั้น สูงกว่า MAE ตอน test ปกติ เกิน **2 วัน** (ตามที่ canvas ตั้งไว้)
- **นโยบายเทรนใหม่:** เมื่อพบ drift ตามเกณฑ์ข้างบน (ตาม canvas คือ MAE เกิน threshold 2 วันติดกัน) ให้แจ้ง Slack แล้วรัน `python src/pipeline.py`

### E. ตัวแปรสภาพแวดล้อม

| ชื่อ | ใช้ทำอะไร | ค่าเริ่มต้น |
|---|---|---|
| `MLFLOW_TRACKING_URI` | ที่เก็บ MLflow | `sqlite:///mlflow.db` (ถ้าใช้ docker compose = `http://mlflow:5000`) |
| `SLACK_WEBHOOK_URL` | ส่ง alert | ไม่ตั้ง = พิมพ์ลง log เฉยๆ |
| `CANDIDATES` | จำกัดโมเดลที่เทรน (ของเดิมใน train.py) | ทุกตัว |
| `GIT_COMMIT` | บันทึกเวอร์ชันโค้ดตอนอยู่ใน Docker | `unknown` |

---

## 4. งานรายคน

### 4.1 tharathep-kku — scaffold, ตรวจ PR, integration

**PR 1: `scaffold` (ทำคืนนี้ ภายใน 1 ชั่วโมง ทุกคนรอ PR นี้)**

1. `src/alerts.py` stub ตามสัญญา A:
   ```python
   """Slack alerts. Stub: thirawatv-sketch fills in the body, keep these signatures."""

   def send_alert(title: str, detail: str = '') -> None:
       print(f'[ALERT] {title} {detail}')


   def notify_validation_failure(detail: str, payload: dict | None = None) -> None:
       send_alert('Invalid prediction request rejected', detail)
   ```
2. `docker-compose.yml` เพิ่มใน service `api` → `environment:` บรรทัด `SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL:-}`
3. `.gitignore` เพิ่ม `logs/` และ `reports/`
4. (ถ้าอยากให้ API รับโหลดได้) พิจารณาเพิ่ม `--workers` ใน CMD ของ Dockerfile หลัง manatsanun วัด load test แล้ว ไม่ต้องทำตอนนี้
5. merge เองได้ทันที (แล้วบอกกลุ่มในแชต: "scaffold เข้า main แล้ว ทุกคน pull")

**ตลอดโปรเจกต์:** ตรวจ PR ทุกอัน รับคำขอแก้ไฟล์ที่ห้ามแตะ (`requirements.txt`, `README.md` ฯลฯ)

**PR 2: `integration` (อา. 4 ต.ค.)**
1. อัปเดต `README.md`: ลิงก์ไป `docs/*.md` ทุกไฟล์, ส่วน "วิธีรันทั้งระบบ", ตาราง "เครื่องมือแต่ละหน้าที่ + เหตุผล" (Version Control, Containerization, Data Validation, Experiment Tracking, Model Registry, Orchestration, Serving, Monitoring, CI/CD)
2. ซ้อมรันจากเครื่องเปล่า: โคลน repo ใหม่ที่โฟลเดอร์อื่น แล้วทำตาม README ล้วนๆ (compose → train → api) จดทุกจุดที่ติด
3. รวบรวมหลักฐานจาก MLflow UI: ภาพเทียบ run ทั้ง 4 (Compare), หน้า registry ที่เห็น alias/tag, ผล rollback → ใส่ใน `docs/img/` (ส่งให้ TonDanc ใส่รายงาน)

**ตรวจก่อนเปิด PR:** `docker compose config` ไม่ error, `python src/test_schema.py` ผ่าน

---

### 4.2 manatsanun — test case, `/metrics`, logging, load test

**PR 1: `test-cases` (ทำก่อน ศ. 2 ต.ค. เสร็จภายในคืนนี้ เพราะ CI รอ)**

สร้าง `tests/cases/` ใส่ไฟล์ JSON payload 1 order ต่อไฟล์ ใช้ชื่อฟิลด์ตามคลาส `Order` ใน `api.py`:
- `good_normal.json`: ข้อมูลปกติ (เอาแบบ `GOOD` ใน `src/test_schema.py`)
- `bad_missing_customer_lat.json`: ขาด `customer_lat`
- `bad_state_xx.json`: `customer_state = "XX"`
- `bad_negative_weight.json`: `total_weight_g = -5`
- `bad_outside_brazil.json`: `customer_lat = 40`
- `bad_wrong_type.json`: `n_items = "abc"`

สร้าง `tests/check_cases.py` (stdlib + pandas + `schema.py` ไม่ใช้ pytest):
- **โหมดปกติ (ไม่มี argument):** อ่าน `tests/cases/*.json` ไฟล์ขึ้นต้น `good_` ต้องผ่าน `input_schema.validate`, ขึ้นต้น `bad_` ต้องถูกปฏิเสธ (จับ `SchemaError`/`SchemaErrors`) ผิดตัวไหนให้ `exit 1` พร้อมบอกชื่อไฟล์ — **ไฟล์ที่ขาด `customer_lat` ให้ตัดฟิลด์ออกจริง ไม่ใช่ใส่ null**
- **โหมด `--url http://localhost:8000`:** ยิงทุกไฟล์ด้วย `urllib` ไปที่ `/predict` `good_` ต้องได้ 200, `bad_` ต้องได้ 422 (ใช้เป็นชุดทดสอบวันนำเสนอ)

อย่าใช้ library ใหม่ ถ้าอยากได้ `requests` ให้ใช้ `urllib.request` แทน

**ตรวจก่อนเปิด PR:** `python tests/check_cases.py` พิมพ์ว่าผ่านทุกไฟล์ (รันจากโฟลเดอร์หลัก)

**PR 2: `serving-metrics`** (หลัง `scaffold` merge)

แก้ `src/api.py` อย่างเดียว (เป็นเจ้าของ):

1. เพิ่ม `from alerts import notify_validation_failure` (ไฟล์มีอยู่แล้วจาก scaffold)
2. **เก็บ metrics ในหน่วยความจำ ไม่เพิ่ม library:** `collections.deque(maxlen=1000)` เก็บเวลา (ms) ของ `/predict` ล่าสุด + ตัวนับ `requests_total`, `errors_total`, `rejected_total`; คำนวณ p50/p95 ด้วย `numpy.percentile` (มีอยู่แล้ว)
3. ครอบเวลาใน `/predict` ด้วย `time.perf_counter()`
4. เพิ่ม `GET /metrics` ตามสัญญา B (ชื่อคีย์ตรงเป๊ะ)
5. **Logging:** ใช้ `logging` มาตรฐาน พิมพ์ 1 บรรทัดต่อ request: เวลา, ผลลัพธ์ (ok/rejected/error), latency ms, model_version
6. **ส่งแจ้งเตือนเมื่อข้อมูลเสีย — มี 2 ทางที่ต้องจับให้ครบ:**
   - ข้อมูลผิดกฎ Pandera: ใน `except (pe.SchemaError, pe.SchemaErrors)` เดิม เรียก `notify_validation_failure(str(exc), payload)` ก่อน `raise HTTPException`
   - **ข้อมูลขาดฟิลด์ (เช่นขาด `customer_lat`):** FastAPI/pydantic ตีกลับ 422 ก่อนถึง Pandera จึงไม่เข้า `except` ข้างบน ต้องเพิ่ม `@app.exception_handler(RequestValidationError)` (จาก `fastapi.exceptions`) ที่เรียก `notify_validation_failure` แล้วคืน `JSONResponse(status_code=422, content={'detail': exc.errors()})` (ใช้ `jsonable_encoder` ถ้ามี error ที่ serialize ไม่ได้) และนับ `rejected_total` ทั้งสองทาง
7. เรื่อง demo: canvas เขียนว่าขาด `customer_zip_code` แต่ API รับ lat/lng ไม่รับ zip จึงใช้ **ขาด `customer_lat`** แทน และให้ระบุเหตุผลนี้ในรายงาน

**โฟลเดอร์ `loadtest/` (ไฟล์ใหม่)**
- `loadtest/run.py` ใช้ stdlib (`concurrent.futures.ThreadPoolExecutor` + `urllib.request`) ยิง `POST /predict` ด้วย payload จาก `tests/cases/good_normal.json` พารามิเตอร์: `--url`, `--requests` (ค่าเริ่มต้น 2000), `--concurrency` (ค่าเริ่มต้น 20)
- พิมพ์ผล: จำนวนสำเร็จ/ผิดพลาด, **P50, P95 (ms), throughput (req/s)**, error rate
- **ประกาศ SLO (ใส่ใน `docs/serving-metrics.md`):** P95 ≤ 200 ms, error rate < 1%, throughput ≥ 50 req/s (ปรับหลังวัดจริงได้ แต่ต้องประกาศก่อนแล้วเทียบ ถ้าไม่ผ่านให้เขียนตรงๆ และแจ้ง tharathep เพื่อเพิ่ม `--workers`)
- เขียนผลลงตารางใน `docs/serving-metrics.md` พร้อมวิธีรัน, เครื่องที่ใช้ทดสอบ, และเหตุผลเลือกรูปแบบ **real-time API** (ต้องตอบทันทีตอน checkout)

**ตรวจก่อนเปิด PR:**
```bash
docker compose up -d mlflow && docker compose run --rm train && docker compose up -d api
curl localhost:8000/metrics
python tests/check_cases.py --url http://localhost:8000     # ต้องผ่านทุกไฟล์ (บอกว่า API ทำตามที่คาดไว้)
python loadtest/run.py --url http://localhost:8000
```
ต้องเห็นบรรทัด `[ALERT]` ใน log ของ api เมื่อยิงไฟล์ `bad_*`

**ถ้าไม่ทัน:** ทำ `/metrics` + load test ก่อน (คะแนนส่วน 5) แล้วค่อยเก็บ logging ละเอียด

---

### 4.3 thirawatv-sketch — CI/CD และ Slack alert

**PR 1: `slack-alert`** (แก้ `src/alerts.py` อย่างเดียว เริ่มได้ทันทีหลัง scaffold)

1. สร้าง Slack Incoming Webhook (Slack workspace ของกลุ่ม → Apps → Incoming Webhooks) **เก็บ URL ไว้ส่งให้กลุ่มทางแชตส่วนตัว ห้ามลง repo**
2. เติมเนื้อหาใน `send_alert`: อ่าน `os.environ.get('SLACK_WEBHOOK_URL')`
   - ถ้ามี: `POST` JSON `{"text": f"*{title}*\n{detail}"}` ด้วย `urllib.request` (timeout 3 วินาที)
   - ถ้าไม่มี: พิมพ์ `[ALERT] ...` และเขียนต่อท้าย `logs/alerts.log` (สร้างโฟลเดอร์ด้วย `os.makedirs('logs', exist_ok=True)`)
   - **ครอบ `try/except Exception` ทั้งหมด เพื่อไม่ให้โยน error ออกมา**
   - ตัด `detail` ให้ไม่เกิน ~1000 ตัวอักษร ก่อนส่ง
3. `notify_validation_failure` ส่ง title "Invalid prediction request rejected" และ detail ที่รวมชื่อคอลัมน์ผิด + payload (ตัดสั้น)
4. เขียน `docs/slack-alert.md`: วิธีตั้งค่า, ภาพข้อความ Slack จริง, อธิบายว่าทำไมต้องไม่โยน exception

**ตรวจก่อนเปิด PR:** `SLACK_WEBHOOK_URL=<url> python -c "import sys; sys.path.insert(0,'src'); import alerts; alerts.send_alert('test','hello')"` ต้องขึ้นใน Slack จริง และเมื่อไม่ตั้ง env ต้องไม่ error

**PR 2: `ci`** (หลัง `test-cases` merge แล้ว)

สร้าง `.github/workflows/ci.yml` (trigger: `pull_request` และ `push` ที่ `main`, และ `workflow_dispatch` มี input `candidates` ค่าเริ่มต้น `dummy_median,hgb_default`) และ `requirements-dev.txt` (ใส่ `ruff` pin เวอร์ชัน)

ใช้ Python 3.11 (ตรงกับ Dockerfile) ติดตั้ง `requirements.txt` + `requirements-dev.txt` ทำ 3 job (หรือ 3 step ที่แยกชัด) ให้เห็นในหน้า Actions ว่าด้านไหนล้ม:

| ด้าน | คำสั่ง | ล้มเมื่อ |
|---|---|---|
| **คุณภาพโค้ด** | `ruff check src tests loadtest` | โค้ดผิดกฎ |
| **ความถูกต้องของข้อมูล** | `python src/test_schema.py` และ `python tests/check_cases.py` | schema ไม่ปฏิเสธข้อมูลเสีย หรือปฏิเสธข้อมูลดี |
| **เกณฑ์คุณภาพโมเดล** | `CANDIDATES=${{ inputs.candidates || 'dummy_median,hgb_default' }} python src/train.py` แล้ว `python src/registry.py promote` | gate ปฏิเสธ (exit 1) |

หมายเหตุสำคัญ:
- ใน CI ไม่มี MLflow server → ใช้ค่าเริ่มต้น `sqlite:///mlflow.db` ได้เลย
- ส่ง `GIT_COMMIT: ${{ github.sha }}` เป็น env
- รัน job โมเดลหลัง job ข้อมูลผ่านแล้วเท่านั้น (`needs:`)
- ตั้ง `timeout-minutes` (เช่น 20) กันค้าง

**หลักฐานที่ต้องเก็บ (กรรมการดูทั้งรอบผ่านและไม่ผ่าน):**
- **รอบเขียว:** PR ปกติ
- **รอบแดง 3 แบบ แยกตามด้าน** (ทำใน branch ทิ้ง ห้าม merge):
  - โค้ด: เพิ่ม `import os` ที่ไม่ใช้ใน branch ทดสอบ ruff จะแดง
  - ข้อมูล: ในสำเนาของ `test_schema.py` ลบเงื่อนไขหนึ่งใน `schema.py` ของ branch ทดสอบ (เช่นลบ `LAT` ของ `customer_lat`) ให้ test จับไม่ได้
  - โมเดล: กด **Run workflow** (workflow_dispatch) ใส่ `candidates = dummy_median` → gate ปฏิเสธเพราะโมเดลไม่ชนะ dummy จึง exit 1
- ถ่ายภาพหน้า Actions แต่ละรอบเก็บใน `docs/img/ci-*.png` ส่งไฟล์ให้ TonDanc ใส่รายงาน (ไฟล์ภาพ thirawatv-sketch เป็นคน commit ลง `docs/img/` ได้ ต้องตั้งชื่อขึ้นต้น `ci-` ไม่ซ้ำกับของคนอื่น)
- เขียน `docs/ci.md`: อธิบายแต่ละ job และเหตุผลที่เลือก GitHub Actions

**ตรวจก่อนเปิด PR:** รัน 3 คำสั่งในตารางบนเครื่องตัวเองให้ผ่านก่อน push (`CANDIDATES=dummy_median,hgb_default python src/train.py` ใช้เวลาไม่กี่นาที)

**ถ้าไม่ทัน:** ทำให้เขียวก่อนทั้ง 3 ด้าน แล้วทำรอบแดงอย่างน้อยด้านโมเดล (ง่ายสุดและแสดงการทำงานของ gate)

---

### 4.4 keerati-chawong — Monitoring และ drift

**สร้าง `src/monitor.py`, `requirements-monitor.txt`, `docs/monitoring.md`**

เครื่องมือ: **Evidently** (pin เวอร์ชันใน `requirements-monitor.txt` หลัง `pip install` ได้แล้ว `pip freeze | findstr evidently`) ถ้าติดตั้ง/เรียกใช้ไม่ได้ภายใน 1 ชั่วโมง ให้เขียนเองด้วย `scipy.stats.ks_2samp` (scipy ติดมากับ scikit-learn อยู่แล้ว) ข้อกำหนดอนุญาตให้ "เขียนเอง"

**ทำอะไร (ใช้ฟังก์ชันจาก `train.py` ได้โดยไม่แก้: `from train import load_splits, xy, MODEL_NAME, TRACKING_URI, DATA_PATH`):**

1. **Reference** = train split จาก `load_splits()`
2. **Data Drift:** เทียบ reference กับ `--current <csv>` บนฟีเจอร์ `total_weight_g`, `distance_km` (ต้องคำนวณด้วย `features.add_features`), `total_price`, `total_freight` ตามเกณฑ์ในสัญญา D
3. **Concept Drift:** โหลด `@champion` จาก MLflow (`mlflow.sklearn.load_model(f'models:/{MODEL_NAME}@champion')`) ทำนายบน current แล้วคำนวณ MAE เทียบกับ MAE test ปกติ แล้วเทียบเกณฑ์ 2 วัน
4. **สถานะระบบ:** (ไม่บังคับให้ทำใน monitor แต่ต้องมีในรายงาน) ดึง `GET /metrics` จาก API (สัญญา B) มาแสดง P95 และ error rate ถ้า API เปิดอยู่ ถ้าไม่ได้เปิดให้ข้ามได้
5. **แจ้งเตือน:** เมื่อเกินเกณฑ์ เรียก `from alerts import send_alert` (มี stub ให้แล้ว) พร้อมบอกว่าเป็น Data Drift หรือ Concept Drift และค่าที่วัดได้
6. **Output:** พิมพ์สรุป, เขียน HTML report ลง `reports/` (โฟลเดอร์ถูก gitignore) และ **exit code ตามสัญญา D**
7. **สถานการณ์ทดสอบ:**
   - `python src/monitor.py --current demo_data/normal_orders.csv` → ต้องได้ 0
   - `python src/monitor.py --current demo_data/drift_north.csv` → ต้องได้ 2 (Data Drift)
   - `python src/monitor.py --current demo_data/drift_blackfriday.csv` → ต้องได้ 3 (Concept Drift) *ถ้า Black Friday ไม่เกินเกณฑ์ 2 วันจริง ให้รายงานตัวเลขตามจริง แล้วเสนอเกณฑ์ที่เหมาะสมกับกลุ่ม อย่าปรับตัวเลขให้ดูผ่านโดยไม่บอก*

**ไม่ต้องรอ TonDanc:** วันนี้ (ศ.) ใช้ val split เป็น `--current` ไปก่อนเพื่อให้โค้ดทำงาน พอ `demo_data/*.csv` เข้ามาแล้ว (ส. ช่วงเช้า) ค่อยเปลี่ยนไปใช้

**`docs/monitoring.md` ต้องมี:** เกณฑ์แจ้งเตือนแต่ละข้อ (ตารางในสัญญา D), นโยบายเทรนใหม่, วิธีแยก Data Drift กับ Concept Drift, ตาราง/ภาพผลของ 3 สถานการณ์ข้างบน, เหตุผลที่เลือกเครื่องมือ

**ตรวจก่อนเปิด PR:** รัน 3 คำสั่งในข้อ 7 ให้ได้ exit code ตรงตามที่ระบุ (`echo $?` ใน bash หรือ `$LASTEXITCODE` ใน PowerShell)

**ถ้าไม่ทัน:** ทำ Data Drift (KS) + Concept Drift (MAE) แบบเขียนเองก่อน ไม่ต้องทำ HTML report

---

### 4.5 Phonnatcha-kku — Pipeline แบบ DAG

**สร้าง `src/pipeline.py`, `requirements-dag.txt`, `docs/pipeline.md`**

เครื่องมือแนะนำ: **Prefect** (ตัวแปร `@flow`/`@task` รันในเครื่องได้โดยไม่ต้องมี server; Airflow ตั้งค่ายากเกินเวลาที่เหลือ) pin เวอร์ชันใน `requirements-dag.txt` หลังติดตั้งได้

**DAG (ลำดับเต็ม):**
```
validate_data -> train -> gate(promote) -> smoke_test (ไม่บังคับ)
```

1. **`validate_data`** เรียก `load_splits(path)` จาก `train.py` (รับ `--data <csv>` ค่าเริ่มต้นคือ `DATA_PATH`) ถ้า Pandera ปฏิเสธจะ **หยุด DAG ทั้งหมด** ก่อน train → exit 2 (นี่คือ demo "ข้อมูลเสียแล้วระบบหยุด": ใช้ `--data demo_data/bad_orders.csv`)
2. **`train`** เรียก `python src/train.py` ด้วย `subprocess.run([sys.executable, 'src/train.py'], check=True)` (เรียกผ่าน subprocess เพราะ `train.py` ใช้ `if __name__ == '__main__'` ไม่ใช่ฟังก์ชันให้ import) ส่ง env ต่อ (`CANDIDATES`, `MLFLOW_TRACKING_URI`, `GIT_COMMIT`) ถ้า `GIT_COMMIT` ไม่ตั้ง ให้ดึงด้วย `git rev-parse HEAD`
3. **`gate`** เรียก `python src/registry.py promote` ถ้า return code ≠ 0 ให้ flow จบด้วย exit 3 (แต่ต้องรายงานชัดว่า "gate ปฏิเสธ" ไม่ใช่ crash) และไม่ถือว่าเป็นบั๊ก
4. **`smoke_test` (ทำเมื่อมีเวลา):** ถ้ามี env `API_URL` ให้เรียก `GET {API_URL}/health` และพิมพ์เวอร์ชันที่ API ใช้ (ถ้าเพิ่งเลื่อน `@champion` ต้อง restart API ก่อน ให้พิมพ์เตือน ไม่ต้องสั่ง restart เอง)
5. **คำสั่งเดียว:** `python src/pipeline.py` (ได้เหมือน `docker compose` ใน README)
6. หากเวลาเหลือ: แสดงภาพกราฟ DAG (Prefect UI `prefect server start`, หรือภาพ screenshot ที่ run สำเร็จ) ใส่ `docs/img/dag-*.png`

**ข้อควรรู้เรื่อง "จากข้อมูลดิบ":** สคริปต์ใน `raw_data + Data prepair/` ใช้ path `archive/clean/...` ซึ่งไม่ตรงกับโครงสร้าง repo และไฟล์ดิบไม่อยู่ใน Docker image ดังนั้น **DAG เริ่มจาก `cleaned_data/feature extraction/shipping_distance_duration.csv`** และให้เขียนข้อนี้ตรงๆ ใน `docs/pipeline.md` (ถ้ามีเวลา ทำ task `prepare_data` ที่เป็นตัวเลือก `--from-raw` ได้ แต่ไม่ใช่งานบังคับ)

**MLflow server หรือ sqlite:** DAG ใช้ `MLFLOW_TRACKING_URI` ที่ตั้งไว้ ถ้าไม่ตั้งจะเป็น sqlite ในเครื่อง ใช้ได้ทั้งสองแบบ

**ตรวจก่อนเปิด PR:**
```bash
pip install -r requirements.txt -r requirements-dag.txt
python src/pipeline.py                                  # exit 0 หรือ 3 (gate) อย่างใดอย่างหนึ่ง ไม่ใช่ crash
python src/pipeline.py --data demo_data/bad_orders.csv  # หยุดที่ validate, exit 2, ไม่มี run ใหม่ใน MLflow
```
(ไฟล์ `demo_data/bad_orders.csv` มาจาก TonDanc ถ้ายังไม่มา ให้สร้างไฟล์ทดสอบเองชั่วคราวนอก repo แล้วไม่ต้อง commit)

**ถ้าไม่ทัน:** ทำ 3 task หลัก (validate → train → gate) แล้วเขียน `docs/pipeline.md` ให้ครบ ข้ามข้อ 4 และ 6

---

### 4.6 TonDanc — ข้อมูล Demo, แผนภาพ, รายงาน

**`demo_data/make_demo_data.py` (ทำก่อน ศ. 2 ต.ค. เสร็จภายในคืนนี้ เพราะ keerati และ Phonnatcha รอ)**

อ่าน `cleaned_data/feature extraction/shipping_distance_duration.csv` สร้างไฟล์ 4 ไฟล์ตามสัญญา C ใน `demo_data/` (รันจากโฟลเดอร์หลัก: `python demo_data/make_demo_data.py`)
- ใช้ `random_state=42` เพื่อให้ได้ผลซ้ำเดิม
- `normal_orders.csv`: สุ่มจาก test split (ใช้ `from train import load_splits` หรือคำนวณการแบ่ง 85% ท้ายด้วยตัวเอง ให้ตรงกับ `time_split`)
- `drift_north.csv`, `drift_blackfriday.csv`: กรองตามสัญญา C
- `bad_orders.csv`: สุ่ม 50 แถวปกติ แล้วทำให้เสีย 3 แบบ (น้ำหนักติดลบ, `customer_state='XX'`, `customer_lat=40`)
- เช็ค: ไฟล์ปกติผ่าน `input_schema.validate`, `bad_orders.csv` ถูกปฏิเสธ (เขียน assert 2 บรรทัดท้ายสคริปต์)

**เอกสารที่ต้องเขียน (ทั้งหมดอยู่ใน `docs/`)**

1. `docs/architecture.md`: แผนภาพสถาปัตยกรรมทั้งระบบ (เขียนด้วย Mermaid ในไฟล์ หรือภาพจาก draw.io ใส่ `docs/img/architecture.png`) ต้องมี: ข้อมูล → Pandera → train (MLflow tracking) → registry (gate, `@champion`) → FastAPI ใน Docker → ผู้ใช้, monitoring (Evidently) ← API, Slack alert, GitHub Actions, DAG ครอบทั้งหมด **ถามแต่ละคนให้ตรวจว่าส่วนของตัวเองถูก**
2. `docs/demo-script.md`: สคริปต์สาธิต 12 นาที พร้อมคำสั่งทีละข้อและใครพูดตอนไหน (ทุกคนมีส่วน): (1) ข้อมูลปกติ → ได้ ETA, (2) ข้อมูลเสีย → ถูกปฏิเสธ + Slack, (3) drift → monitor แจ้งเตือน, (4) pipeline รันใหม่ + gate, (5) rollback, (6) CI รอบแดง/เขียน
3. `docs/report.md`: รายงานรวม โครงอ้างอิงจากเกณฑ์ 8 ส่วน (ตาราง "หัวข้อ → ไฟล์ที่เป็นแหล่ง") ต้องมีหัวข้อ: โจทย์/Canvas, ข้อมูลและ schema, โมเดลและเหตุผลเลือก, tracking/registry, serving + SLO, monitoring + drift + นโยบายเทรนใหม่, CI/CD, DAG, **เหตุผลที่เลือกเครื่องมือแต่ละตัว**, **ส่วนที่ใช้ AI ช่วยเขียนโค้ด (ทุกคนส่งข้อความมาให้)**, ภาคผนวกหลักฐาน
4. เก็บภาพทั้งหมดใน `docs/img/` ตั้งชื่อขึ้นต้นด้วยหมวด (`mlflow-`, `ci-`, `dag-`, `monitor-`, `slack-`, `arch-`) กันชื่อซ้ำ

**ตรวจก่อนเปิด PR:** `python demo_data/make_demo_data.py` รันซ้ำได้ผลเหมือนเดิม

**ถ้าไม่ทัน:** ทำ `demo_data` ก่อน (คนอื่นรออยู่) ตามด้วยแผนภาพ แล้วรายงานให้ครบเท่าที่เวลาเหลือ รายงานเป็นของส่งท้ายทาง อา. 4 ต.ค.

---

## 5. ใครต้องรอใคร (กัน deadlock)

| งาน | รอ | ทำอะไรไปก่อนได้ |
|---|---|---|
| ทุกคน | `scaffold` (tharathep) | แตก branch และเขียนโค้ดไปก่อนได้ แค่ยังไม่ merge |
| manatsanun `serving-metrics` | `scaffold` | เขียน metrics ได้เลย ใช้ `from alerts import ...` หลัง pull scaffold |
| thirawatv `ci` | `test-cases` (manatsanun) | เขียน 2 ใน 3 job (โค้ด, โมเดล) ไปก่อน |
| keerati `monitor` | `demo_data` (TonDanc) | ใช้ val split ไปก่อน |
| Phonnatcha `pipeline` | `demo_data/bad_orders.csv` (TonDanc) | ทำ validate/train/gate ไปก่อน |
| TonDanc รายงาน | ทุกคน | เขียนโครงและส่วนที่เสร็จแล้วก่อน |

---

## 6. เช็คลิสต์เทียบเกณฑ์คะแนน (ใช้ตรวจก่อนส่ง)

| ส่วน | ข้อที่ต้องมีหลักฐาน | ที่อยู่ | ผู้รับผิดชอบ |
|---|---|---|---|
| 1 | Canvas, Optimizing/Gating metric | `To do list.md`, README, `docs/report.md` | TonDanc |
| 2 | Schema + ข้อมูลเสียหยุด+แจ้งเตือน | `schema.py`, `tests/`, `docs/slack-alert.md` | manatsanun, thirawatv |
| 2 | Training-Serving Skew | `features.py` + Pipeline เดียว | tharathep (อธิบายในรายงาน) |
| 3 | Baseline + เทียบ ≥3 รอบ + เหตุผล | ภาพ MLflow Compare | tharathep |
| 4 | Tracking 6 อย่าง, registry, gate, rollback | MLflow UI, `registry.py` | tharathep |
| 5 | API ใน container, P50/P95/throughput เทียบ SLO, `/health`, metrics/logs | `docs/serving-metrics.md` | manatsanun |
| 6 | Monitoring (คุณภาพ+ระบบ), แยก Data/Concept drift, เกณฑ์, retrain | `docs/monitoring.md` | keerati |
| 6 | CI/CD 3 ด้าน เขียว+แดง | `docs/ci.md`, `docs/img/ci-*` | thirawatv |
| 7 | DAG รันซ้ำทั้งกระบวนการ | `docs/pipeline.md` | Phonnatcha |
| 7 | Branch/PR + รันจากเครื่องเปล่า | ประวัติ PR, README | ทุกคน, tharathep |
| 8 | รายงาน, แผนภาพ, สาธิต, test case | `docs/report.md`, `docs/architecture.md`, `docs/demo-script.md`, `tests/` | TonDanc, ทุกคน |

---

## 7. ความเสี่ยงที่รู้อยู่แล้ว

- **`api.py` แก้โดย manatsanun คนเดียว:** คนอื่นต้องการเปลี่ยนอะไรใน API ให้บอก manatsanun
- **เวลา train ใน CI:** ถ้าช้าเกินให้ลด `candidates` เป็น `dummy_median,hgb_default`
- **gate รอบแรกของเครื่องเปล่า:** ยังไม่มี champion ดังนั้นด่าน "ดีกว่า champion 5%" ข้ามไป เหลือแค่ชนะ dummy และ P95 < 200 ms
- **Evidently เวอร์ชัน API เปลี่ยนบ่อย:** pin เวอร์ชัน และมีทางสำรองคือ `scipy.stats.ks_2samp`
- **ข้อมูลดิบไม่ reproducible จาก repo:** เขียนตรงๆ ในรายงาน อย่าอ้างว่า DAG เริ่มจากข้อมูลดิบ
- **อาจารย์ให้อธิบายโค้ดทุกบรรทัด:** ทุกคนต้องอ่านและอธิบายโค้ดของตัวเองได้ รวมส่วนที่ AI ช่วยเขียน
