## ส่วนที่ใช้ AI ช่วย

| สมาชิก | ไฟล์/ส่วน | AI ช่วยทำอะไร |
|---|---|---|
| TonDanc | `demo_data/make_demo_data.py`, `demo_data/report-demo.md`, ร่างรายงานนี้ | Claude Code ช่วยเขียนสคริปต์สร้างข้อมูลจำลอง, README ของข้อมูล และร่างรายงาน |
| tharathep-kku | README, registry, MLflow | ใช้ Claude Code ทำ README โครงสร้าง ช่วยใบ้การทำและช่วยทำโค้ด, บอกใน Claude กด commit |
| manatsanun | `src/api.py`, `loadtest/run.py`, `docs/serving-metrics.md`, `tests/check_cases.py` | Codex ช่วยเขียนโค้ดเก็บ metrics/log, สคริปต์ทดสอบ API และร่างเอกสารประกอบ |
| thirawatv-sketch | `.github/workflows/ci.yml`, `src/alerts.py`, `docs/ci.md`, `docs/slack-alert.md`, `requirements-dev.txt` | Codex ช่วยเขียน CI/CD, ระบบแจ้งเตือน Slack และเอกสารประกอบ |
| keerati-chawong | `clean_loma.ipynb`, `evidently/`, `src/monitor.py`, `docs/monitoring.md` | Claude Code ช่วยเขียน `monitor.py`, ตรวจผล drift, ร่างเอกสาร, อธิบายค่าใน Evidently และโค้ด plot ใน `clean_loma` |
| Phonnatcha-kku | `train.py`, `docs/pipeline.md`, `src/pipeline.py`, `src/prepare.py` | Claude Code, Gemini — ช่วยแนะนำโมเดล, แนะนำการทำงานของ DAG แบบ Prefect, สอนการใช้ Prefect เขียนเชื่อมยังไง, แก้ไข error |

## สมาชิก

| รหัส | ชื่อ | GitHub | งานหลัก |
|---|---|---|---|
| 673380320-6 | นายธราเทพ เบญจพรหม | tharathep-kku | train, MLflow tracking/registry, schema, Docker, ตรวจ PR |
| 673380307-8 | นายกีรติ ชาวงษ์ | keerati-chawong | เตรียมข้อมูล order, monitoring และ drift |
| 673380327-2 | นางสาวพรนัชชา ทราบรัมย์ | Phonnatcha-kku | ออกแบบโมเดล, pipeline DAG, `prepare.py`, deploy |
| 673380361-2 | นายแดนชล ประไชโย | TonDanc | ข้อมูลดิบ, ข้อมูล demo, รายงาน |
| 673380338-7 | นางสาวมนัสนันท์ วรสุทธิพงษ์ | manatsanun | FastAPI, test cases, metrics, load test |
| 673380314-1 | นายถิรวัฒน์ วิเศษโวหาร | thirawatv-sketch | Dockerfile, Slack alert, CI/CD |
