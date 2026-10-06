# CI: ตรวจคุณภาพโค้ด ข้อมูล และโมเดล

`.github/workflows/ci.yml` (GitHub Actions) แยกเป็น 3 job เพื่อให้เห็นทันทีว่าด้านไหนล้ม

| Job | คำสั่งหลัก | ล้มเมื่อ | timeout |
|---|---|---|---|
| Code quality | `ruff check src tests loadtest` | โค้ดผิดกฎ เช่น import ที่ไม่ใช้ ชื่อที่ไม่ได้ประกาศ | 5 นาที |
| Data quality | `python src/test_schema.py` และ `python tests/check_cases.py` | schema ยอมรับข้อมูลเสีย หรือปฏิเสธข้อมูลดี | 10 นาที |
| Model quality | `python src/train.py` แล้ว `python src/registry.py promote` | train พัง หรือ gate ปฏิเสธโมเดล (exit 1) | 20 นาที |

- **Trigger:** เปิดหรืออัปเดต PR, push เข้า `main`, หรือกด **Run workflow** (`workflow_dispatch`) ซึ่งมี input `candidates` ค่าเริ่มต้น `dummy_median,hgb_default`
- **ลำดับ:** Model quality มี `needs: [code-quality, data-quality]` จึงเทรนหลังโค้ดและข้อมูลผ่านแล้วเท่านั้น
- **Environment:** Python 3.11 (ตรงกับ Dockerfile), Ubuntu 24.04 Code quality ลงแค่ `requirements-dev.txt` (ruff pin `0.15.1`) อีกสอง job ลง `requirements.txt` + `requirements-dev.txt` ใช้ pip cache
- **MLflow:** ใช้ `sqlite:///mlflow.db` บน runner ของแต่ละ job (ไม่มี server) ส่ง `GIT_COMMIT=${{ github.sha }}` เพื่อบันทึกเวอร์ชันโค้ด
- รอบเก่าของ PR เดียวกันถูกยกเลิกเมื่อมีรอบใหม่

**Model gate ใน CI:** runner เริ่มจาก registry ว่าง ไม่มี champion เดิม จึงตรวจแค่ "ชนะ dummy" และ "P95 < 200 ms" CI แค่พิสูจน์ว่าโมเดลผ่านเกณฑ์ ไม่ได้เปลี่ยน champion ของระบบจริง (การ deploy ทำผ่าน `pipeline.py --deploy`)

**ข้อยกเว้น ruff:** `tests/check_cases.py` ตั้ง `sys.path` ก่อน import `schema` เพื่อให้รันจากโฟลเดอร์หลักได้ จึงยกเว้น `E402` เฉพาะไฟล์นี้ (`--per-file-ignores 'tests/check_cases.py:E402'`)

## ตรวจบนเครื่องตัวเอง

ใช้ Python 3.11 รันจากโฟลเดอร์หลัก ใช้ฐาน MLflow ชั่วคราวเพื่อไม่ไปเปลี่ยน champion ของฐานที่ API ใช้

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m ruff check src tests loadtest --target-version py311 --per-file-ignores 'tests/check_cases.py:E402'
python src/test_schema.py
python tests/check_cases.py
CANDIDATES=dummy_median,hgb_default MLFLOW_TRACKING_URI=sqlite:///$(mktemp -u).db GIT_COMMIT=$(git rev-parse HEAD) \
  sh -c 'python src/train.py && python src/registry.py promote'
```

PowerShell (บรรทัดสุดท้าย):

```powershell
$env:CANDIDATES = 'dummy_median,hgb_default'
$env:MLFLOW_TRACKING_URI = 'sqlite:///' + (Join-Path ([IO.Path]::GetTempPath()) "ci-$(New-Guid).db").Replace('\', '/')
$env:GIT_COMMIT = git rev-parse HEAD
python src/train.py; if ($?) { python src/registry.py promote }
Remove-Item Env:CANDIDATES, Env:MLFLOW_TRACKING_URI, Env:GIT_COMMIT
```

## ทำให้ CI แดงเพื่อทดสอบ

| ด้าน | วิธี | ผลที่ต้องเห็น |
|---|---|---|
| โค้ด | เพิ่มไฟล์ที่มี `import os` แต่ไม่ใช้ เข้า ruff | `F401`, exit 1, job โมเดลถูกข้าม |
| ข้อมูล | ปิด range check ของ `customer_lat` ชั่วคราว แล้วรัน `test_schema.py` | `AssertionError` ที่ `rejects(customer_lat=40.0)`, job โมเดลถูกข้าม |
| โมเดล | Run workflow ด้วย `candidates = dummy_median` | `REJECTED: MAE 5.057 does not beat dummy 5.057`, exit 1 |

ผลจริงบน GitHub Actions ทั้งรอบเขียวและแดง พร้อมภาพและลิงก์ อยู่ใน [report.md](report.md#ภาคผนวก-ก-ci-รอบผ่านและไม่ผ่าน)
