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

## Demo ขาดฟิลด์

ใช้ `tests/cases/bad_missing_customer_lat.json` ต้องได้ HTTP 422 และ `[ALERT]`

Canvas ระบุว่าขาด `customer_zip_code` แต่ API รับ lat/lng และไม่มีฟิลด์ zip จึงใช้ขาด `customer_lat` ซึ่งเป็นฟิลด์บังคับแทน ให้ใช้เหตุผลนี้ในรายงานรวมด้วย
