"""DAG ของโปรเจกต์ด้วย Prefect:  validate_data -> train -> gate -> smoke_test (ถ้าตั้ง API_URL)

รันจากโฟลเดอร์หลักของ repo:
  python src/pipeline.py                                  # ข้อมูลปกติ
  python src/pipeline.py --data demo_data/bad_orders.csv  # ข้อมูลเสีย -> หยุดที่ validate
  API_URL=http://localhost:8000 python src/pipeline.py    # หลัง gate ผ่าน เช็ค /health ของ API ด้วย

Exit code (ตาม GUIDE สัญญา D):  0 = ทุกขั้นสำเร็จ,  2 = validate ไม่ผ่าน,  3 = gate ปฏิเสธโมเดล

เทียบกับ TFX ใน Lecture 11:
  validate_data = ExampleValidator (ใช้ Pandera schema ใน schema.py เป็น "สัญญา" ของข้อมูล)
  train         = Trainer          (train.py เทรนหลายโมเดล + log MLflow + ตั้ง @challenger)
  gate          = Evaluator+Pusher (registry.py promote: ผ่านเกณฑ์ = "blessed" -> @champion)
"""
import argparse
import json
import os
import subprocess
import sys
from urllib.error import URLError
from urllib.request import urlopen

import mlflow
from pandera.errors import SchemaError, SchemaErrors
from prefect import flow, task

from train import DATA_PATH, MODEL_NAME, TRACKING_URI, git_commit, load_splits


@task
def validate_data(path: str) -> None:
    # ใช้ load_splits ตัวเดียวกับที่ train.py ใช้ -> ถ้า Pandera เจอข้อมูลเสียจะโยน SchemaError ออกมา
    load_splits(path)
    print(f'ข้อมูลผ่าน schema: {path}')


@task
def train() -> None:
    # train.py ไม่มีฟังก์ชันให้ import (โค้ดอยู่ใต้ if __name__ == '__main__') จึงเรียกเป็นโปรแกรมแยก
    # env ส่งต่อให้อัตโนมัติ (CANDIDATES, MLFLOW_TRACKING_URI); เติม GIT_COMMIT ถ้ายังไม่ได้ตั้ง
    env = {**os.environ, 'GIT_COMMIT': os.environ.get('GIT_COMMIT') or git_commit()}
    subprocess.run([sys.executable, 'src/train.py'], check=True, env=env)  # check=True: train พัง = task พัง


@task
def gate() -> bool:
    # registry.py promote คืน 0 ถ้าโมเดลผ่านด่าน (ได้เป็น @champion) และไม่ใช่ 0 ถ้าถูกปฏิเสธ
    result = subprocess.run([sys.executable, 'src/registry.py', 'promote'])
    return result.returncode == 0


@task
def smoke_test(api_url: str) -> None:
    # ไม่บังคับ: ถาม API ที่รันอยู่ว่าใช้โมเดลเวอร์ชันไหน เทียบกับ @champion ที่เพิ่งเลื่อน (ไม่ restart ให้เอง)
    mlflow.set_tracking_uri(TRACKING_URI)
    champion = mlflow.MlflowClient().get_model_version_by_alias(MODEL_NAME, 'champion').version
    try:
        with urlopen(api_url.rstrip('/') + '/health', timeout=5) as response:
            health = json.load(response)
    except (URLError, OSError, ValueError) as e:  # API ไม่ได้เปิด = เตือนเฉยๆ ไม่ทำให้ flow ล้ม
        print(f'WARN: smoke test เรียก {api_url}/health ไม่ได้ ({e})')
        return
    print(f'API /health: {health}')
    if str(health.get('version')) != str(champion):  # sqlite store gives int, API JSON gives str
        print(f'WARN: API ยังใช้ v{health.get("version")} แต่ @champion คือ v{champion} '
              '-> restart API เพื่อโหลดตัวใหม่ (docker compose restart api)')


@flow(name='delivery-eta-pipeline')
def pipeline(data: str = DATA_PATH) -> int:
    # ลำดับการเรียกในฟังก์ชันนี้คือเส้นของ DAG: ขั้นถัดไปเริ่มได้เมื่อขั้นก่อนหน้าสำเร็จเท่านั้น
    try:
        validate_data(data)
    except (SchemaError, SchemaErrors) as e:  # Errors = แปลงชนิดข้อมูลไม่ได้ (เช่น n_items="abc")
        print(f'STOP: ข้อมูลไม่ผ่าน validate ไม่เทรนต่อ\n{e}')
        return 2
    train()
    if not gate():
        print('STOP: gate ปฏิเสธโมเดลใหม่ (@champion ตัวเดิมยังใช้งานต่อ)')
        return 3
    if os.environ.get('API_URL'):
        smoke_test(os.environ['API_URL'])
    print('DONE: โมเดลใหม่ผ่าน gate และเป็น @champion แล้ว (restart API เพื่อโหลดตัวใหม่)')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default=DATA_PATH, help='CSV ที่จะตรวจด้วย schema ก่อนเทรน')
    sys.exit(pipeline(parser.parse_args().data))
