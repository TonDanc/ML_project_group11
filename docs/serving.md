# การให้บริการ: API, metrics, SLO และ load test

## รูปแบบการให้บริการ

เลือก **real-time API** (FastAPI ใน Docker) เพราะหน้าเว็บต้องแสดง ETA ทันทีตอนลูกค้า checkout คำขอ 1 ครั้ง = 1 order ไม่ใช้ batch เพราะไม่รู้ล่วงหน้าว่าลูกค้าจะสั่งอะไร

API โหลดโมเดล `@champion` จาก MLflow registry ตอนเริ่ม (โมเดลไม่ได้อยู่ใน image) และใช้ Pipeline ก้อนเดียวกับตอนเทรน จึงไม่มีโค้ดแปลงข้อมูลซ้ำ

## Endpoints

| Endpoint | ทำอะไร |
|---|---|
| `GET /` | หน้าเว็บทดลองกรอก order (`src/index.html`) |
| `GET /docs` | เอกสาร API อัตโนมัติของ FastAPI |
| `POST /predict` | รับ 1 order คืน `predicted_delivery_days` และ `model_version` ข้อมูลไม่ผ่าน schema ได้ HTTP 422 |
| `GET /health` | `{"status": "ok" \| "unavailable", "model": "delivery_eta", "version": "1"}` |
| `GET /metrics` | ตัวนับและ latency (ด้านล่าง) |

```bash
curl -X POST http://localhost:8000/predict -H "Content-Type: application/json" \
  -d '{"customer_state":"SP","seller_state":"SP","customer_lat":-23.5,"customer_lng":-46.6,"seller_lat":-23.6,"seller_lng":-46.7,"n_sellers":1,"n_items":2,"total_price":100.0,"total_freight":15.0,"total_weight_g":800.0,"estimated_delivery_days":10,"order_purchase_timestamp":"2018-05-01T10:00:00"}'
```

## Metrics

เก็บใน RAM ไม่เพิ่ม library และไม่เขียนฐานข้อมูล (`src/api.py`):

- middleware `record_predict_metrics` จับเวลาทุกคำขอ `/predict` ด้วย `time.perf_counter()` และเก็บเวลาใน `finally` จึงนับได้แม้เกิด error
- `latencies_ms = deque(maxlen=1000)` เก็บเวลา 1,000 คำขอล่าสุด รวมคำขอสำเร็จ ถูกปฏิเสธ และผิดพลาด
- `requests_total`, `rejected_total` (HTTP 4xx), `errors_total` (HTTP 5xx) นับสะสมตั้งแต่ process เริ่ม
- `GET /metrics` คำนวณ P50/P95 ด้วย `np.percentile(values, [50, 95])` ถ้ายังไม่มีข้อมูลคืน 0

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

**ข้อจำกัด:** API รัน 8 workers แต่ละ worker มีตัวนับของตัวเอง ค่าจาก `/metrics` จึงเป็นของ worker ที่รับคำขอนั้นเท่านั้น ใช้ดู P50/P95 เป็นตัวอย่างได้ แต่ตัวนับรวมต้องดูจาก log หรือ load test และเพราะนับคำขอที่ถูกปฏิเสธ (จบเร็ว) ด้วย P50 อาจต่ำกว่าเวลาทำนายจริงเล็กน้อย

## Logging และการแจ้งเตือนข้อมูลเสีย

ทุกคำขอ `/predict` พิมพ์ 1 บรรทัด: เวลา, ผล `ok/rejected/error`, `latency_ms`, `model_version`

ข้อมูลเสียมี 2 ทาง ทั้งสองเรียก `notify_validation_failure` (ส่ง Slack ดู [monitoring.md](monitoring.md#การแจ้งเตือน-slack)) แล้วคืน 422:

1. ขาดฟิลด์หรือชนิดผิด: Pydantic ปฏิเสธก่อนถึง `predict` จัดการใน `handle_request_validation_error`
2. ผิดกฎ เช่นน้ำหนักติดลบ: Pandera ปฏิเสธใน `except (pe.SchemaError, pe.SchemaErrors)`

ตรวจข้อมูลก่อนตรวจว่าโมเดลพร้อม ข้อมูลเสียจึงได้ 422 และแจ้งเตือนแม้โมเดลยังไม่โหลด

สาธิตข้อมูลขาดฟิลด์ใช้ `tests/cases/bad_missing_customer_lat.json` (Canvas เขียนว่าขาด `customer_zip_code` แต่ API รับพิกัดแทน zip จึงใช้ `customer_lat` ซึ่งเป็นฟิลด์บังคับแทน)

## SLO

| ตัวชี้วัด | เป้าหมาย |
|---|---|
| P95 latency | ≤ 200 ms |
| Error rate | < 1% |
| Throughput | ≥ 50 req/s |

`monitor.py --api-url` อ่าน `/metrics` แล้วแจ้งเตือนเมื่อ P95 หรือ error rate เกินเกณฑ์ (ดู [monitoring.md](monitoring.md))

## การตั้งค่า workers

`Dockerfile` รัน `uvicorn --workers 8` และตั้ง `OMP_NUM_THREADS=1` เฉพาะ API:

- 1 คำขอใช้ CPU ~45 ms (Pandera validate 33.7 ms + predict 10.9 ms) worker เดียวรับได้ไม่เกิน ~22 req/s
- `HistGradientBoostingRegressor` ใช้ OpenMP สร้าง thread เท่าจำนวน CPU ในทุก worker ทุก worker จึงแย่ง CPU กัน การตั้ง `OMP_NUM_THREADS=1` ให้ 1 process ใช้ 1 thread แล้วขยายด้วยจำนวน process แทน
- 8 workers ใช้ RAM ~1.5 GB เครื่องที่มี CPU น้อยกว่า 8 ให้ลด `--workers` ให้ไม่เกินจำนวน CPU
- service `train` ใช้ image เดียวกันแต่ไม่ตั้ง `OMP_NUM_THREADS` เพื่อใช้ทุก core ตอนเทรน

ผลทดลองปรับทีละตัวแปรอยู่ใน [report.md](report.md#ภาคผนวก-ข-load-test-ทุกรอบ)

## Load test: `loadtest/run.py`

ใช้ stdlib (`ThreadPoolExecutor` + `urllib.request`) ยิง `POST /predict` ด้วย `tests/cases/good_normal.json`

```bash
python loadtest/run.py --url http://localhost:8000                                   # ค่าเริ่มต้น 2,000 คำขอ พร้อมกัน 20
python loadtest/run.py --url http://localhost:8000 --requests 2000 --concurrency 20
```

- P50/P95 วัดฝั่ง client รวมเวลาเครือข่ายและเวลาต่อคิว จึงต่างจาก `/metrics`
- Throughput = จำนวนคำขอ / เวลาทั้งหมด, Error rate = คำขอที่ไม่ได้ 2xx / ทั้งหมด

### ผลล่าสุด

6 ต.ค. 2569, clone ใหม่ + build image ใหม่, Windows 11 + Docker Desktop, 12 CPU, workers = 8, 2,000 คำขอ / concurrency 20

| รอบ | สำเร็จ / ผิดพลาด | P50 (ms) | P95 (ms) | Throughput (req/s) | เทียบ SLO |
|---|---|---:|---:|---:|---|
| 1 | 2,000 / 0 | 94.45 | 228.54 | 179.12 | throughput และ error rate ผ่าน, **P95 เกิน 200 ms เล็กน้อย** |
| 2 | 2,000 / 0 | 95.10 | 223.38 | 182.77 | เหมือนรอบ 1 |

ผลรอบนี้ดีกว่ารอบวันที่ 4 ต.ค. (P95 ~680 ms, ~58 req/s) บนเครื่องเดียวกันมาก ยังไม่ได้หาสาเหตุ ต้องวัดซ้ำก่อนสรุป

**ทำไม P95 ยังไม่ผ่านที่ concurrency 20:** เวลารอเฉลี่ย ≈ concurrency / throughput (Little's law) ทางลดต่อ: ลดเวลา Pandera ซึ่งเป็น 3/4 ของเวลาต่อคำขอ, รวมหลายคำขอเป็น batch (validate + predict 100 แถวใช้ 37 ms ใกล้เคียง 1 แถว) หรือ scale ออกหลายเครื่อง

### ทดสอบ API ทั้งชุดด้วยคำสั่งเดียว

ต้องมี `@champion` ก่อน (`docker compose up -d mlflow && docker compose run --rm train`) แล้วรันใน cmd, Git Bash หรือ PowerShell 7:

```bash
docker compose up -d --build api && curl.exe -s --retry 30 --retry-all-errors --retry-delay 2 http://localhost:8000/health && python tests/check_cases.py --url http://localhost:8000 && python loadtest/run.py --url http://localhost:8000 && curl.exe -s http://localhost:8000/metrics
```

ต้องเห็น case ผ่าน 6/6 และบรรทัด `[ALERT]` ใน `docker compose logs api` 5 บรรทัด (ไฟล์ `bad_*` 5 ไฟล์)
