# การวัดผล API และทดสอบโหลด

เลือกใช้ **real-time API** เพราะต้องตอบเวลาจัดส่งโดยประมาณให้ลูกค้าทันทีตอน checkout

## Metrics เก็บตรงไหนและทำงานอย่างไร

เก็บใน RAM ไม่เพิ่ม library และไม่เขียนฐานข้อมูล:

- `latencies_ms = deque(maxlen=1000)` เก็บเวลาของ `/predict` ล่าสุด 1,000 ครั้ง เมื่อเต็มจะทิ้งค่าที่เก่าสุดเอง รวมคำขอสำเร็จ ถูกปฏิเสธ และผิดพลาด
- `requests_total` นับคำขอ `/predict` ทั้งหมด
- `rejected_total` นับ HTTP 4xx รวม 422 จาก Pydantic และ Pandera
- `errors_total` นับ HTTP 5xx และข้อผิดพลาดที่ทำให้ประมวลผลไม่สำเร็จ
- ใน `record_predict_metrics` เริ่มจับเวลาด้วย `time.perf_counter()` ก่อนส่งต่อคำขอ แล้วเก็บเวลาใน `finally` ด้วยสูตร `(เวลาสิ้นสุด - เวลาเริ่ม) * 1000` หน่วย ms จึงนับได้แม้เกิดข้อผิดพลาด
- ใน `metrics` ใช้ `np.percentile(values, [50, 95])` คำนวณ P50/P95 ถ้ายังไม่มีข้อมูลจะคืนค่า 0

P50 คือเวลาที่ประมาณครึ่งหนึ่งของคำขอใช้เวลาไม่เกินค่านี้ ส่วน P95 คือเวลาที่ประมาณ 95% ของคำขอใช้เวลาไม่เกินนี้

`GET /metrics` คืนชื่อคีย์ตรงสัญญา B:

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

ตัวเลขข้างบนเป็นตัวอย่าง `count` คือจำนวนเวลาที่เก็บไว้ สูงสุด 1,000 ส่วนตัวนับนับสะสมตั้งแต่เริ่ม process ทุกค่าเริ่มใหม่เมื่อ restart หากใช้หลาย workers แต่ละ worker มี metrics ของตัวเอง

`/health` ใช้คีย์เดิม `status`, `model`, `version`

## Logging และแจ้งเตือน

แต่ละคำขอ `/predict` มีบรรทัดสรุปจาก logging มาตรฐาน: เวลา ผลลัพธ์ `ok/rejected/error`, `latency_ms` และ `model_version`

ข้อมูลเสียมีสองทาง ทั้งสองเรียก `notify_validation_failure` ก่อนคืน 422:

1. ขาดฟิลด์หรือชนิดข้อมูลผิด: Pydantic ปฏิเสธก่อนเข้า `predict` จัดการใน `handle_request_validation_error`
2. ผิดกฎ เช่นน้ำหนักติดลบ: Pandera ปฏิเสธ จัดการใน `except (pe.SchemaError, pe.SchemaErrors)`

middleware นับ rejected จากสถานะคำตอบครั้งเดียวต่อคำขอ ส่วน `[ALERT]` เป็นข้อความแจ้งเตือนเพิ่มเติม ตรวจข้อมูลก่อนตรวจว่าโมเดลพร้อมหรือไม่ เพื่อให้ข้อมูลเสียยังได้ 422 และแจ้งเตือนแม้โมเดลไม่พร้อม

## SLO ที่ประกาศก่อนวัด

| ตัวชี้วัด | เป้าหมาย |
| --- | --- |
| P95 | ≤ 200 ms |
| Error rate | < 1% |
| Throughput | ≥ 50 req/s |

ต้องผ่านครบทั้งสามข้อ หากไม่ผ่านให้บันทึกตรง ๆ และแจ้ง tharathep เพื่อพิจารณาเพิ่ม `--workers` แล้ววัดใหม่ หากปรับเป้าหมายให้บันทึกเหตุผลและประกาศก่อนวัดรอบถัดไป

## วิธีรันก่อนเปิด PR

รันจากโฟลเดอร์หลักทีละคำสั่ง ตรวจว่าคำสั่งก่อนหน้าสำเร็จก่อนทำต่อ:

```powershell
 docker compose up -d mlflow
 docker compose run --rm train
 docker compose up -d --build api
 curl.exe http://localhost:8000/health
 curl.exe http://localhost:8000/metrics
 python tests/check_cases.py --url http://localhost:8000
 docker compose logs api
 python loadtest/run.py --url http://localhost:8000
 curl.exe http://localhost:8000/metrics
```

ใช้ `--build` เพื่อให้ API ใช้โค้ดล่าสุด รอ `/health` มี `status: ok` ก่อนทดสอบ ต้องเห็น case ทุกไฟล์ผ่านและ `[ALERT]` เมื่อยิง `bad_*`

load test ใช้ stdlib `ThreadPoolExecutor` และ `urllib.request` ส่ง payload จาก `tests/cases/good_normal.json` ค่าเริ่มต้น 2,000 คำขอ พร้อมกันสูงสุด 20 คำขอ ปรับได้ด้วย:

```powershell
python loadtest/run.py --url http://localhost:8000 --requests 2000 --concurrency 20
```

แสดงจำนวนสำเร็จ/ผิดพลาด, P50, P95, throughput และ error rate:

- สำเร็จคือ HTTP 2xx ผิดพลาดคือสถานะอื่นหรือเชื่อมต่อไม่ได้
- P50/P95 ใช้เวลาคำขอทั้งหมด รวมรับคำตอบและเครือข่าย จึงอาจต่างจาก `/metrics`
- Throughput = จำนวนคำขอทั้งหมด / เวลาทดสอบทั้งหมด หน่วย req/s
- Error rate = จำนวนผิดพลาด / จำนวนคำขอทั้งหมด × 100%

## ผลทดสอบจริง

| วันที่ | เครื่อง (OS, CPU, RAM, workers) | คำขอ / concurrency | สำเร็จ / ผิดพลาด | P50 / P95 (ms) | Throughput (req/s) | Error rate | เทียบ SLO |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-03 | Windows + Docker Desktop, CPU/RAM ยังไม่ได้บันทึก, API workers=1 | 2,000 / 20 | 2,000 / 0 | 952.09 / 1166.74 | 21.03 | 0.00% | ไม่ผ่าน: P95 เกิน 200 ms และ throughput ต่ำกว่า 50 req/s |

ผลรันจริงจาก terminal:

- `docker compose run --rm train` ผ่าน และ promote `delivery_eta` version 1 เป็น `@champion`
- `/health` ตอบ `{"status":"ok","model":"delivery_eta","version":"1"}`
- `/metrics` ตอบคีย์ตามสัญญา B
- `python tests/check_cases.py --url http://localhost:8000` ผ่านทุกไฟล์ 6/6
- `docker compose logs api` เห็น `[ALERT]` ทั้งกรณีขาด `customer_lat` และข้อมูลผิดกฎ validation
- `python loadtest/run.py --url http://localhost:8000` สำเร็จ 2,000, ผิดพลาด 0

สรุป SLO: error rate ผ่าน แต่ P95 และ throughput ยังไม่ผ่าน ต้องแจ้ง tharathep เพื่อพิจารณาเพิ่ม `--workers` แล้ววัดใหม่

## รอบ 2: เพิ่ม workers ตาม GUIDE 4.1 ข้อ 4 (2026-10-04)

### หาสาเหตุก่อนแก้

วัดเวลาต่อ 1 คำขอภายใน container (`docker compose exec api python ...`):

| ขั้น | เวลา |
| --- | --- |
| Pandera `input_schema.validate` 1 แถว | 33.7 ms |
| `model.predict` 1 แถว | 10.9 ms |

1 คำขอใช้ CPU ราว 45 ms และ worker เดียวมี GIL ตัวเดียว จึงรับได้ไม่เกินราว 22 req/s ตรงกับที่วัดได้ คำขอที่เกินจะต่อคิว P95 จึงสูงถึงเกือบ 1 วินาที

### ทดลองทีละตัวแปร (เครื่องเดียวกัน, 2,000 คำขอ, concurrency 20)

เครื่อง: Windows 11 + Docker Desktop 29.8, 12 CPU, RAM ให้ Docker 7.5 GB

| ตั้งค่า | P50 / P95 (ms) | Throughput (req/s) | หมายเหตุ |
| --- | --- | --- | --- |
| `--workers 4` | 868.72 / 1459.39 | 22.34 | ไม่ดีขึ้นเลย container มี 318 threads |
| `--workers 4` + `OMP_NUM_THREADS=1` | 476.17 / 970.65 | 40.16 | |
| `--workers 8` + `OMP_NUM_THREADS=1` | 250.41 / 641.26 | 68.05 | RAM api 1.5 GB |
| `--workers 12` + `OMP_NUM_THREADS=1` | 209.26 / 552.21 | 78.66 | RAM api 2.2 GB ได้เพิ่มแค่ 15% |

ทำไม 4 workers ไม่ช่วย: `HistGradientBoostingRegressor` ใช้ OpenMP ซึ่งสร้าง thread เท่าจำนวน CPU (12) ในทุก worker ทุก worker จึงแย่ง CPU กันเอง ตั้ง `OMP_NUM_THREADS=1` ให้ 1 process ใช้ 1 thread แล้วขยายด้วยจำนวน process แทน (scale ด้วย concurrency ตาม Lecture 8)

เลือก **8 workers + `OMP_NUM_THREADS=1`** (แก้ CMD ใน `Dockerfile` ใส่ `env OMP_NUM_THREADS=1` เฉพาะคำสั่งของ API เพราะ service `train` ใช้ image เดียวกันและควรใช้ทุก core ตอนเทรน) เพราะ 12 workers ได้เพิ่มน้อยแต่ใช้ RAM เพิ่ม 0.7 GB ถ้าเครื่องมี CPU น้อยกว่านี้ให้ลด `--workers` ให้ไม่เกินจำนวน CPU

### ผลหลังแก้ (image ที่ build จาก Dockerfile ใหม่)

| วันที่ | เครื่อง (OS, CPU, RAM, workers) | คำขอ / concurrency | สำเร็จ / ผิดพลาด | P50 / P95 (ms) | Throughput (req/s) | Error rate | เทียบ SLO |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-04 | Windows 11 + Docker Desktop, 12 CPU, 7.5 GB, API workers=8 | 2,000 / 20 | 2,000 / 0 | 299.96 / 690.13 | 57.77 | 0.00% | throughput และ error rate ผ่าน, **P95 ยังไม่ผ่าน** |
| 2026-10-04 | เครื่องเดียวกัน รันซ้ำ, workers=8 | 2,000 / 20 | 2,000 / 0 | 301.53 / 672.82 | 58.46 | 0.00% | เหมือนรอบก่อน |
| 2026-10-04 | เครื่องเดียวกัน, workers=8 | 2,000 / 8 | 2,000 / 0 | 89.18 / 225.56 | 70.19 | 0.00% | ใกล้ P95 แต่ยังเกิน 200 ms |

ผลเปลี่ยนตามภาระเครื่องตอนวัด (รอบทดลองข้างบนได้ 68 req/s, รอบนี้ 58 req/s) ผลรันเดียวกัน: `check_cases.py --url` ผ่าน 6/6 และ `docker compose logs api` มี `[ALERT]` 5 บรรทัด (ตรงกับไฟล์ `bad_*` 5 ไฟล์)

ทำไม P95 ยังไม่ผ่านที่ concurrency 20: เวลารอโดยเฉลี่ย ≈ concurrency / throughput = 20 / 58 ≈ 345 ms (Little's law) จะได้ P95 ≤ 200 ms ที่ 20 คำขอพร้อมกันต้องรับได้ราว 150 req/s ขึ้นไป ซึ่งเกินกำลัง CPU 12 core เมื่อ 1 คำขอใช้ 45 ms ทางที่เหลือ (ยังไม่ได้ทำ ต้องแก้ `api.py`): ลดเวลา Pandera ซึ่งเป็น 3/4 ของเวลาต่อคำขอ หรือรวมหลายคำขอเป็น batch แบบ TF Serving ใน Lab 8 (วัดแล้ว validate+predict 100 แถวพร้อมกันใช้ 37 ms ใกล้เคียง 1 แถว) หรือ scale ออกหลายเครื่อง (horizontal scaling)

`/metrics` หลังเพิ่ม workers: แต่ละ worker มีตัวนับของตัวเอง คำขอ `/metrics` แต่ละครั้งได้ค่าของ worker ที่รับคำขอนั้นเท่านั้น (เช่นเห็น `requests_total` 249 จาก ~2,006) P50/P95 ยังใช้เป็นตัวอย่างได้ แต่ตัวนับรวมต้องดูจาก log หรือจากผล load test

### ทดสอบด้วยคำสั่งเดียว

ครั้งแรกต้องมี `@champion` ก่อน: `docker compose up -d mlflow && docker compose run --rm train`

จากนั้นรันคำสั่งเดียว (cmd, Git Bash หรือ PowerShell 7 ซึ่งรองรับ `&&`):

```bash
docker compose up -d --build api && curl.exe -s --retry 30 --retry-all-errors --retry-delay 2 http://localhost:8000/health && python tests/check_cases.py --url http://localhost:8000 && python loadtest/run.py --url http://localhost:8000 && curl.exe -s http://localhost:8000/metrics
```

`curl --retry` รอจน API โหลดโมเดลเสร็จ ทุกขั้นต่อด้วย `&&` ถ้าขั้นไหนล้มจะหยุดทันที ไม่ใส่ `train` ในคำสั่งนี้เพราะการ train รอบที่สองมักไม่ผ่าน gate (ต้องดีกว่า champion 5%) แล้วคืน exit 1

## Demo ขาดฟิลด์

ใช้ `tests/cases/bad_missing_customer_lat.json` ต้องได้ HTTP 422 และ `[ALERT]`

Canvas ระบุว่าขาด `customer_zip_code` แต่ API รับ lat/lng และไม่มีฟิลด์ zip จึงใช้ขาด `customer_lat` ซึ่งเป็นฟิลด์บังคับแทน ให้ใช้เหตุผลนี้ในรายงานรวมด้วย
