# Monitoring และ drift — `src/monitor.py`

ผู้รับผิดชอบ: keerati-chawong (branch `monitoring`)

## สรุปสั้น

คำสั่งเดียวตอบ 3 คำถาม: **ข้อมูลขาเข้าเปลี่ยนไหม (Data Drift) → โมเดลแม่นน้อยลงไหม (Concept Drift) → ต้องเทรนใหม่หรือยัง**
ถ้าเกินเกณฑ์จะแจ้งเตือนผ่าน `alerts.send_alert` (Slack หรือ `logs/alerts.log`) และคืน exit code ให้ขั้นถัดไปใช้ต่อ

```
ข้อมูลช่วงล่าสุด (--current)
        │
        ├─ 1) Data Drift     PSI ของ input เทียบ train split   (Evidently)
        ├─ 2) Concept Drift  MAE ของ @champion เทียบ MAE บน test split
        ├─ 3) สถานะระบบ      GET /metrics ของ API เทียบ SLO   (เมื่อใส่ --api-url)
        │
        └─ เกินเกณฑ์ → send_alert → exit 2 / 3 → เทรนใหม่ด้วย python src/pipeline.py
```

## วิธีรัน (จากโฟลเดอร์หลักของ repo)

ต้องมี `@champion` ใน MLflow ก่อน (`python src/train.py` แล้ว `python src/registry.py promote`)

```bash
pip install -r requirements.txt -r requirements-monitor.txt

python src/monitor.py --current demo_data/normal_orders.csv       # exit 0  ไม่พบ drift
python src/monitor.py --current demo_data/drift_north.csv         # exit 2  Data Drift
python src/monitor.py --current demo_data/drift_blackfriday.csv   # exit 3  Concept Drift
python src/monitor.py --current demo_data/normal_orders.csv --api-url http://localhost:8000   # ดู P95 / error rate ของ API ด้วย
```

ดู exit code: `echo $?` (bash) หรือ `$LASTEXITCODE` (PowerShell)

| Exit code | ความหมาย |
|---|---|
| 0 | ไม่พบ drift |
| 2 | **Data Drift**: การกระจายของ input เปลี่ยน |
| 3 | **Concept Drift**: input เหมือนเดิม แต่โมเดลคลาดเคลื่อนเกินเกณฑ์ |
| 1 | รันไม่สำเร็จ (ไม่มี `@champion`, หาไฟล์ไม่เจอ, ข้อมูลไม่ผ่าน schema, ใส่ argument ผิด) |

ผลที่ได้ทุกครั้ง: ตารางสรุปบนหน้าจอ, HTML report ของ Evidently ที่ `reports/monitor_<ชื่อไฟล์>.html` (โฟลเดอร์ถูก gitignore) และข้อความแจ้งเตือนเมื่อเกินเกณฑ์

## เกณฑ์แจ้งเตือน

ตัวเลขทั้งหมดเป็นค่าคงที่ต้นไฟล์ `src/monitor.py` แก้ที่เดียว

| ด้าน | วัดอะไร | เกณฑ์ | ค่าคงที่ | แจ้งเตือน |
|---|---|---|---|---|
| Data Drift | PSI ของ `total_weight_g` และ `distance_km` เทียบ train split | PSI > 0.2 คอลัมน์ใดคอลัมน์หนึ่ง | `PSI_LIMIT` | `Data Drift detected`, exit 2 |
| Concept Drift | MAE ของ `@champion` บนข้อมูลช่วงนั้น | MAE > MAE ตอน test ปกติ + 2 วัน (3.389 + 2 = **5.389 วัน**) และ input ไม่ drift | `MAE_MARGIN` | `Concept Drift detected`, exit 3 |
| เทรนใหม่ | MAE รายวัน (เฉพาะวันที่มี order ≥ 30) | เกินเกณฑ์ **2 วันติดกัน** หรือพบ Data Drift | `RETRAIN_DAYS`, `MIN_ORDERS_PER_DAY` | บรรทัด `retrain: YES` และอยู่ในข้อความแจ้งเตือน |
| ระบบ | `latency_ms.p95` และ `errors_total / requests_total` จาก `GET /metrics` | P95 > 200 ms หรือ error rate ≥ 1% (SLO เดียวกับ [serving-metrics.md](serving-metrics.md)) | `P95_LIMIT_MS`, `ERROR_RATE_LIMIT` | `API SLO breached` (ไม่เปลี่ยน exit code) |

`total_price`, `total_freight` และ `delivery_days` คำนวณ PSI/KS และอยู่ใน HTML report ด้วย แต่แสดงเป็น `info` ไม่ใช้ตัดสิน

**PSI อ่านอย่างไร:** แบ่งค่าเป็นช่วง แล้ววัดว่าสัดส่วนข้อมูลในแต่ละช่วงต่างจาก reference แค่ไหน < 0.1 ถือว่าเหมือนเดิม, 0.1–0.2 เริ่มขยับ, > 0.2 เปลี่ยนชัดเจน

## แยก Data Drift กับ Concept Drift อย่างไร

| | Data Drift | Concept Drift |
|---|---|---|
| อะไรเปลี่ยน | การกระจายของ input (เช่น ระยะทาง) | ความสัมพันธ์ระหว่าง input กับเวลาส่งจริง |
| วัดจาก | PSI ของ feature | MAE ของโมเดลเทียบค่าปกติ |
| ต้องรู้คำตอบจริงไหม | ไม่ต้อง ตรวจได้ทันทีที่ order เข้า | ต้องรอจนของถึงมือลูกค้า (เฉลี่ยประมาณ 8–13 วัน) จึงรู้ช้ากว่า |
| ตัวอย่างในโครงงาน | ลูกค้าภาคเหนือ ระยะทาง median 2,379 กม. (train 450 กม.) | สัปดาห์ Black Friday ระยะทางและน้ำหนักเท่าเดิม แต่ส่งช้ากว่าที่โมเดลทายเฉลี่ย 3.6 วัน |

ลำดับการตัดสินใน `monitor.py`:

1. input drift (PSI > 0.2) → **Data Drift** (exit 2) แม้ MAE จะเกินเกณฑ์ด้วย เพราะเมื่อ input ย้ายไปอยู่ช่วงที่โมเดลเห็นน้อย MAE ที่สูงขึ้นอธิบายได้ด้วย input ที่เปลี่ยน ยังสรุปไม่ได้ว่าความสัมพันธ์เปลี่ยน
2. input ไม่ drift แต่ MAE เกินเกณฑ์ → **Concept Drift** (exit 3) order หน้าตาเหมือนเดิมแต่ใช้เวลาส่งต่างไป
3. ไม่เข้าทั้งสองข้อ → ไม่พบ drift (exit 0)

## นโยบายเทรนใหม่

| เหตุการณ์ | สิ่งที่ทำ |
|---|---|
| MAE รวมของช่วงเกินเกณฑ์ หรือ PSI > 0.2 | แจ้ง Slack ทันที |
| MAE รายวันเกินเกณฑ์ **2 วันติดกัน** (ตาม Canvas) หรือพบ Data Drift | แจ้ง Slack ว่าต้องเทรนใหม่ แล้วรัน `python src/pipeline.py` |
| MAE เกินวันเดียวแล้วกลับมาปกติ | แจ้งเตือนอย่างเดียว ยังไม่เทรน (วันเดียวอาจเป็น noise) |
| pipeline เทรนเสร็จ | gate ใน `registry.py promote` ตัดสิน: ดีกว่า `@champion` ≥ 5% จึงเลื่อนขั้น ไม่ผ่านก็ใช้ตัวเดิมต่อ |
| โมเดลใหม่ขึ้นแล้วแย่กว่าเดิม | `python src/registry.py rollback` |

`monitor.py` **ไม่สั่งเทรนเอง** มีหน้าที่ตรวจและแจ้ง การเทรนเป็นหน้าที่ของ DAG ต่อกันด้วย exit code:

```bash
python src/monitor.py --current demo_data/drift_blackfriday.csv || python src/pipeline.py
```

PowerShell: `python src/monitor.py --current demo_data/drift_blackfriday.csv; if ($LASTEXITCODE -ne 0) { python src/pipeline.py }`

ทำไมต้อง 2 วันติดกัน: บน test split ปกติ (69 วันที่มี order ≥ 30) MAE รายวันสูงสุดคือ 4.93 วัน ไม่มีวันไหนเกิน 5.389 เลย เกณฑ์นี้จึงไม่แจ้งเตือนผิดบนข้อมูลปกติ ส่วนสัปดาห์ Black Friday เกิน 7 วันติดกัน

## ผลของ 3 สถานการณ์

รันเมื่อ 5 ต.ค. 2569 โมเดล `@champion` v1 (`hgb_default`, test MAE 3.389) reference = train split 66,724 แถว เกณฑ์ MAE = 5.389 วัน

| ข้อมูลที่ป้อน | แถว | PSI `total_weight_g` | PSI `distance_km` | MAE (วัน) | เทียบ test | วันติดกันที่เกินเกณฑ์ | ผล | exit |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| `normal_orders.csv` | 500 | 0.013 | 0.084 | 3.347 | −0.04 | – (ไม่มีวันที่ order ≥ 30) | ไม่พบ drift | **0** |
| `drift_north.csv` | 1,765 | 0.008 | **6.937** | 6.971 | +3.58 | – (ไม่มีวันที่ order ≥ 30) | Data Drift, เทรนใหม่ | **2** |
| `drift_blackfriday.csv` | 3,264 | 0.008 | 0.015 | **6.317** | **+2.93** | **7** | Concept Drift, เทรนใหม่ | **3** |

exit code ตรงกับที่ GUIDE คาดไว้ทั้ง 3 ไฟล์ และ Black Friday เกินเกณฑ์ 2 วันจริง (เกิน 2.93 วัน)

ข้อมูลเทียบเพิ่ม: val split ได้ MAE 4.086 (+0.70) และ PSI ทุกคอลัมน์ ≤ 0.014 จึงไม่ถูกแจ้งเตือน

MAE รายวันของสัปดาห์ Black Friday (เกณฑ์ 5.389):

| วันที่สั่งซื้อ | order | MAE (วัน) | เกินเกณฑ์ |
|---|---:|---:|---|
| 2017-11-20 | 217 | 5.24 | ไม่เกิน |
| 2017-11-21 | 217 | 5.45 | เกิน |
| 2017-11-22 | 187 | 5.89 | เกิน |
| 2017-11-23 | 266 | 5.53 | เกิน |
| 2017-11-24 (Black Friday) | 1,133 | 6.30 | เกิน |
| 2017-11-25 | 479 | 7.61 | เกิน |
| 2017-11-26 | 376 | 6.26 | เกิน |
| 2017-11-27 | 389 | 6.67 | เกิน |

ข้อความแจ้งเตือนที่ได้จริง (ไม่ได้ตั้ง `SLACK_WEBHOOK_URL` จึงลง `logs/alerts.log`):

```
[ALERT] Data Drift detected on drift_north
total_weight_g PSI=0.008, distance_km PSI=6.937 (limit 0.2)
MAE=6.97 days, limit 5.39 (test MAE 3.39 + 2), 0 consecutive days over the limit
Retrain: yes -> python src/pipeline.py
[ALERT] Concept Drift detected on drift_blackfriday
total_weight_g PSI=0.008, distance_km PSI=0.015 (limit 0.2)
MAE=6.32 days, limit 5.39 (test MAE 3.39 + 2), 7 consecutive days over the limit
Retrain: yes -> python src/pipeline.py
```

HTML report ของ Evidently จากรอบวันศุกร์อยู่ใน repo ที่ `evidently/reports/drift_north.html` และ `evidently/reports/drift_blackfriday.html`

## จุดที่ต่างจากสัญญา D ใน GUIDE (ต้องให้กลุ่มรับทราบ)

GUIDE บอกว่าถ้าตัวเลขจริงไม่เป็นตามเกณฑ์ให้รายงานตามจริงแล้วเสนอเกณฑ์ที่เหมาะสม มี 2 ข้อ:

**1. ใช้ PSI ตัดสินอย่างเดียว KS p-value แสดงไว้เป็นข้อมูล**
สัญญา D เขียนว่า "PSI > 0.2 หรือ KS p-value < 0.01" แต่ reference มี 66,724 แถว KS test จึงไวมากจนข้อมูลปกติก็ไม่ผ่าน:

| ข้อมูล | KS p-value `total_weight_g` | KS p-value `distance_km` | ถ้าใช้ KS ตัดสิน |
|---|---:|---:|---|
| `normal_orders.csv` | 0.0001 | 0.0009 | ถูกแจ้งว่า Data Drift (ผิด) |
| val split | 0.000004 | 2×10⁻²³ | ถูกแจ้งว่า Data Drift (ผิด) |
| `drift_blackfriday.csv` | 0.00002 | 0.0051 | ถูกแจ้งว่า Data Drift |

ถ้าใช้ KS ตามตัวอักษร ทุกไฟล์จะได้ Data Drift รวมถึงข้อมูลปกติ จึงแยกสถานการณ์ไม่ได้ PSI วัด "ขนาด" ของการเปลี่ยน ไม่ขึ้นกับจำนวนแถว จึงเหมาะกว่า

**2. MAE เกินเกณฑ์พร้อมกับ input drift รายงานเป็น Data Drift (exit 2) ไม่ใช่ 3**
สัญญา D เขียนว่า "ถ้ามีทั้งสองให้คืน 3" แต่ `drift_north.csv` มี MAE 6.971 ซึ่งเกินเกณฑ์ 5.389 ด้วย ถ้าทำตามตัวอักษรจะได้ exit 3 ไม่ใช่ 2 ตามที่ GUIDE คาด
เหตุผลที่เลือกแบบนี้: ภาคเหนือส่งนานเป็นปกติ (เฉลี่ย 22 วัน) ค่าคลาดเคลื่อนจึงใหญ่ตามไปด้วย เป็นผลจาก input ที่เปลี่ยน ไม่ใช่ความสัมพันธ์ที่เปลี่ยน ข้อความแจ้งเตือนยังแสดง MAE ไว้ครบ

## เหตุผลที่เลือก Evidently

- คำนวณ PSI และ KS ต่อคอลัมน์ให้เลย ไม่ต้องเขียนการแบ่งช่วงเอง และได้ HTML report ที่เห็นการกระจายของ reference เทียบ current ใช้เป็นหลักฐานได้
- เป็น library ของ Python ตัวเดียว (`pip install`) ไม่ต้องตั้ง server หรือ database แบบ Prometheus + Grafana เหมาะกับการตรวจเป็นรอบ (batch) ซึ่งตรงกับงานนี้ เพราะคำตอบจริงมาช้าหลายวันอยู่แล้ว
- pin เวอร์ชัน `evidently==0.7.23` ใน `requirements-monitor.txt` เพราะ API เปลี่ยนบ่อย
- ส่วน MAE, การนับวันติดกัน และการอ่าน `/metrics` เขียนเองด้วย pandas/numpy เพราะเป็นกฎเฉพาะของโครงงาน

## ข้อจำกัด

- **ไฟล์ demo เป็นข้อมูลย้อนหลัง ไม่ใช่ traffic จริง** ตอนใช้งานจริง `--current` ควรเป็น order ช่วง N วันล่าสุดที่รู้วันส่งถึงแล้ว ตอนนี้ API ยังไม่เก็บ payload ลงไฟล์ จึงยังต่อจาก API มาที่ monitor อัตโนมัติไม่ได้
- **สัปดาห์ Black Friday (พ.ย. 2017) อยู่ใน train split** (train คือ 15 ก.ย. 2016 – 16 เม.ย. 2018) โมเดลเคยเห็นแถวเหล่านี้แล้ว MAE 6.317 จึงเป็นค่าที่ดีกว่าความจริง ถ้าเจอเหตุการณ์แบบนี้ครั้งแรก MAE น่าจะสูงกว่านี้
- **`drift_north.csv` กระจายตลอด 2 ปี** วันละไม่กี่ order จึงไม่มีวันไหนถึง 30 order กฎ "2 วันติดกัน" ใช้กับไฟล์นี้ไม่ได้ การเทรนใหม่ของไฟล์นี้มาจาก Data Drift
- **เทรนใหม่ใน demo ใช้ CSV ชุดเดิม** (`pipeline.py` อ่าน `DATA_PATH` เสมอ) โมเดลใหม่จึงไม่ดีขึ้น 5% และ gate จะปฏิเสธ ซึ่งเป็นผลที่ถูกต้อง การเทรนใหม่จะช่วยจริงเมื่อมีข้อมูลช่วงใหม่เข้ามาใน CSV
- **`delivery_days` เทียบ train มี PSI 0.39 แม้ในข้อมูลปกติ** เพราะเวลาส่งเฉลี่ยลดลงตามเวลา (train 13.3 → val 10.4 → test 7.9 วัน) เกณฑ์ MAE จึงอิง test split ซึ่งเป็นช่วงล่าสุด ไม่อิง train
- ยังไม่มีตัวตั้งเวลา ต้องสั่งรันเอง (หรือใส่ใน cron / Prefect schedule ภายหลัง)

## ไฟล์ที่เกี่ยวข้อง

| ไฟล์ | หน้าที่ |
|---|---|
| `src/monitor.py` | ตรวจ drift + สถานะระบบ, แจ้งเตือน, คืน exit code |
| `requirements-monitor.txt` | `evidently==0.7.23` |
| `evidently/check_drift.py` | สคริปต์ทดลองรอบแรก (เทียบ PSI/KS ของ 2 ไฟล์ drift) `monitor.py` ใช้วิธีเดียวกันและเพิ่ม MAE, เกณฑ์, แจ้งเตือน, exit code |
| `src/alerts.py` | `send_alert` (ของ thirawatv-sketch) |
| `demo_data/*.csv` | ข้อมูล 3 สถานการณ์ (ของ TonDanc) |
