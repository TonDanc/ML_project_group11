# CI: code, data and model quality

งานของ `thirawatv-sketch` ตาม GUIDE ส่วน 4.3 ใช้ GitHub Actions เพราะผูกกับ PR ของ repository ได้โดยตรง และแสดงผลแต่ละด้านแยกเป็น job เพื่อให้ทราบว่าต้องแก้ส่วนไหน

## ไฟล์และจุดสำคัญ

- `.github/workflows/ci.yml` กำหนดเหตุการณ์เริ่มตรวจ, environment และ 3 job
- `requirements-dev.txt` pin `ruff==0.15.1` ให้ผล lint ใช้กฎเวอร์ชันเดียวกันทุกครั้ง
- ทุก job ใช้ Python 3.11 ตาม Dockerfile และ Ubuntu 24.04
- เริ่มทำงานเมื่อเปิดหรืออัปเดต PR, push เข้า `main` หรือกด `Run workflow` บนหน้า Actions
- `GIT_COMMIT` รับค่า `github.sha` เพื่อบันทึกเวอร์ชันโค้ด ส่วน `MLFLOW_TRACKING_URI` ใช้ `sqlite:///mlflow.db` ที่อยู่ใน runner ของแต่ละ job
- `needs: [code-quality, data-quality]` ทำให้เริ่ม train หลังการตรวจโค้ดและข้อมูลผ่านแล้วเท่านั้น
- ตั้ง timeout ของ job ไว้ 5, 10 และ 20 นาที และยกเลิกรอบเก่าของ PR เดียวกันเมื่อมีรอบใหม่

CI นี้ train และ promote ในฐานข้อมูลชั่วคราวบน runner เพื่อพิสูจน์ว่าโมเดลผ่านเกณฑ์ การ deploy หรือเปลี่ยน champion ของระบบที่ใช้งานจริงเป็นขั้นตอนของผู้ดูแลระบบ

## สิ่งที่ตรวจ

| Job | คำสั่งหลัก | ความหมายเมื่อไม่ผ่าน |
|---|---|---|
| Code quality | `python -m ruff check src tests` และ `loadtest` เมื่อมีโฟลเดอร์ | พบโค้ดผิดกฎ เช่น import ที่ไม่ใช้ หรือชื่อที่ไม่ได้ประกาศ |
| Data quality | `python src/test_schema.py` และ `python tests/check_cases.py` | schema ยอมรับข้อมูลเสียหรือปฏิเสธข้อมูลดี |
| Model quality | `python src/train.py` แล้ว `python src/registry.py promote` | train มีปัญหา หรือ gate ปฏิเสธโมเดลด้วย exit code ที่ไม่ใช่ 0 |

Code quality ติดตั้งเฉพาะ dev dependencies ส่วน Data และ Model ติดตั้ง `requirements.txt` กับ `requirements-dev.txt` โดยใช้ pip cache ช่วยลดเวลาดาวน์โหลด

### การรองรับโครงสร้าง repo ปัจจุบัน

ขณะสร้าง CI ยังไม่มี `loadtest/` workflow จึงตรวจ `src` และ `tests` ก่อน และรวม `loadtest` เข้า lint อัตโนมัติเมื่อโฟลเดอร์ของเพื่อนเข้ามา

`tests/check_cases.py` ตั้ง `sys.path` ก่อน import `schema` เพื่อให้รันจากโฟลเดอร์หลักได้ จึงยกเว้น `E402` เฉพาะไฟล์นี้ด้วย `--per-file-ignores 'tests/check_cases.py:E402'` กฎอื่นและไฟล์อื่นยังถูกตรวจตามปกติ หากเปลี่ยนวิธี import ในอนาคต สามารถเอาข้อยกเว้นนี้ออกได้

### Model gate

ค่าเริ่มต้น `CANDIDATES=dummy_median,hgb_default` ตาม GUIDE ผู้ดูแลเลือกค่าเองได้จาก input `candidates` ของ `workflow_dispatch` โดยส่ง input ผ่าน environment ให้โปรแกรมอ่าน

`registry.py` เป็นผู้ตรวจว่า MAE ชนะ dummy, P95 ต่ำกว่า 200 ms และถ้ามี champion เดิมต้องดีขึ้นตามเกณฑ์ของระบบ runner ใหม่ไม่มี champion เดิม จึงตรวจเกณฑ์แรกสองข้อ การ gate ปฏิเสธต้องแสดง job ล้มตาม exit code ของสคริปต์

## วิธีตรวจบนเครื่องตัวเอง (PowerShell)

ใช้ Python 3.11 ใน virtual environment แล้วเปิด PowerShell ใหม่และรันจากโฟลเดอร์หลักของโปรเจกต์ หากเรียก `python` ไม่ได้ ให้ใช้เส้นทาง interpreter ของ virtual environment แทน

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
$taskLintTargets = @('src', 'tests')
if (Test-Path -LiteralPath loadtest -PathType Container) { $taskLintTargets += 'loadtest' }
python -m ruff check $taskLintTargets --target-version py311 --per-file-ignores 'tests/check_cases.py:E402'
python src/test_schema.py
python tests/check_cases.py
$env:CANDIDATES = 'dummy_median,hgb_default'
$taskCiDb = Join-Path ([System.IO.Path]::GetTempPath()) ('ml-group11-ci-' + [guid]::NewGuid().ToString('N') + '.db')
$env:MLFLOW_TRACKING_URI = 'sqlite:///' + $taskCiDb.Replace('\', '/')
$env:GIT_COMMIT = git rev-parse HEAD
python src/train.py
python src/registry.py promote
Remove-Item Env:CANDIDATES, Env:MLFLOW_TRACKING_URI, Env:GIT_COMMIT -ErrorAction SilentlyContinue
```

คำสั่งนี้สร้างฐานข้อมูลทดสอบชื่อใหม่ใน Temp เพื่อให้ผลเหมือน runner ใหม่และไม่เปลี่ยน champion ของฐานข้อมูลที่ API ใช้ artifacts ที่สคริปต์สร้างใน `mlruns/` เป็นผลทดสอบในเครื่องและถูก gitignore ไว้แล้ว

## เก็บหลักฐานก่อนส่งงาน

1. รอบเขียว: เปิด PR ปกติ ต้องเห็นทั้ง 3 job ผ่าน เก็บภาพ `docs/img/ci-green.png`
2. รอบแดงด้านโค้ด: ใช้ branch ทดสอบแยก ใส่ import ที่ไม่ใช้ในไฟล์ทดสอบเพื่อให้ Ruff จับได้ เก็บภาพ `docs/img/ci-red-code.png`
3. รอบแดงด้านข้อมูล: ใน branch ทดสอบแยก ถอดข้อจำกัด `customer_lat` ออกจาก schema เพื่อพิสูจน์ว่า test จับได้ เก็บภาพ `docs/img/ci-red-data.png` branch นี้ห้าม merge ตาม GUIDE
4. รอบแดงด้านโมเดล: เมื่อ workflow อยู่บน default branch แล้ว ไปที่ Actions → CI → Run workflow เลือก `candidates=dummy_median` ต้องเห็น Model quality ล้มเพราะไม่ชนะ dummy เก็บภาพ `docs/img/ci-red-model.png`

ต้องเก็บผลจาก Actions จริง ชื่อภาพใช้คำนำหน้า `ci-` และส่งให้ TonDanc ใช้ประกอบรายงาน

## สถานะการตรวจสอบ

ตรวจบน Python 3.11.15 ด้วย dependencies ตาม `requirements.txt` และ `requirements-dev.txt` โดยรัน schema และ train/gate บนสำเนา source/data ใน Temp:

| การตรวจ | ผลในเครื่อง |
|---|---|
| YAML และการเชื่อม job | ผ่าน: trigger ทั้ง 3 แบบ, Python 3.11, input candidates, timeouts และ model job รอ code/data |
| Ruff | ผ่าน โดยใช้ข้อยกเว้น import ตามที่อธิบาย |
| Schema | `schema checks ok` |
| Test cases | ผ่านทั้ง 6 ไฟล์ |
| Train และ gate รอบปกติ | ผ่าน: `hgb_default` test MAE 3.389 วัน, dummy MAE 5.057 วัน, P95 14.6 ms และ `PROMOTED` |
| รอบแดงด้านโค้ดในสำเนาชั่วคราว | import ที่ไม่ใช้ถูกจับด้วย `F401`, exit 1 |
| รอบแดงด้านข้อมูลในสำเนาชั่วคราว | ถอดข้อจำกัด latitude แล้ว schema test จับได้ด้วย `AssertionError`, exit 1 |
| รอบแดงด้านโมเดลในสำเนาชั่วคราว | `dummy_median` อย่างเดียวถูก gate ปฏิเสธ เพราะ MAE 5.057 วันเท่ากับ dummy, exit 1 |

ค่าความเร็วเป็นผลของเครื่องทดสอบนี้ runner บน GitHub จะวัดใหม่และตัดสินผ่าน gate ของตัวเอง ผลในเครื่องยังไม่ใช่รอบ Actions จริงและยังไม่มีภาพหลักฐาน ต้องเก็บตามขั้นตอนข้างบนหลังเปิด PR

## เอกสารอ้างอิง

- [GitHub: setup-python](https://github.com/actions/setup-python)
- [GitHub: checkout](https://github.com/actions/checkout)
- [Ruff: module-import-not-at-top-of-file (E402)](https://docs.astral.sh/ruff/rules/module-import-not-at-top-of-file/)
