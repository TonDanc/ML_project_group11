"""DAG ของโปรเจกต์ด้วย Prefect:  prepare_data -> validate_data -> train -> gate -> deploy (ถ้าใส่ --deploy)

รันจากโฟลเดอร์หลักของ repo:
  python src/pipeline.py                                  # ข้อมูลปกติ
  python src/pipeline.py --data demo_data/bad_orders.csv  # ข้อมูลเสีย -> หยุดที่ validate
  docker compose up -d mlflow && MLFLOW_TRACKING_URI=http://localhost:5050 python src/pipeline.py --deploy
                                                          # คำสั่งเดียวจนถึงการให้บริการ: API โหลด @champion ใหม่

Exit code (ดู docs/pipeline.md):  0 = ทุกขั้นสำเร็จ,  2 = validate ไม่ผ่าน,  3 = gate ปฏิเสธโมเดล,  1 = crash/deploy ไม่สำเร็จ

เทียบกับ TFX ใน Lecture 11:
  prepare_data  = ExampleGen       (prepare.py: ข้อมูลดิบ Olist 8 ไฟล์ -> shipping_distance_duration.csv)
  validate_data = ExampleValidator (ใช้ Pandera schema ใน schema.py เป็น "สัญญา" ของข้อมูล)
  train         = Trainer          (train.py เทรนหลายโมเดล + log MLflow + ตั้ง @challenger)
  gate          = Evaluator+Pusher (registry.py promote: ผ่านเกณฑ์ = "blessed" -> @champion)
  deploy        = Pusher ไปถึง serving (สร้าง API container ใหม่ + รอ /health ตอบ @champion)
"""
import argparse
import json
import os
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import mlflow
from pandera.errors import SchemaError, SchemaErrors
from prefect import flow, task

from prepare import RAW_DIR, prepare
from train import DATA_PATH, MODEL_NAME, TRACKING_URI, git_commit, load_splits

DEPLOY_TIMEOUT_S = 180  # 8 workers each load the model from MLflow on startup


@task
def prepare_data() -> None:
    # ข้อมูลดิบ -> DATA_PATH ที่ train.py อ่าน (ผลเหมือนเดิมทุก byte ถ้าข้อมูลดิบไม่เปลี่ยน)
    prepare(DATA_PATH)


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
def deploy(api_url: str) -> None:
    # API โหลด @champion ตอนเริ่มเท่านั้น -> สร้าง container ใหม่ แล้วรอจน /health ตอบเวอร์ชันที่เพิ่งเลื่อน
    # ต้องตั้ง MLFLOW_TRACKING_URI ให้ชี้ server เดียวกับ API (http://localhost:5050) ไม่งั้นเวอร์ชันจะไม่ตรงกัน
    mlflow.set_tracking_uri(TRACKING_URI)
    champion = str(mlflow.MlflowClient().get_model_version_by_alias(MODEL_NAME, 'champion').version)
    subprocess.run(['docker', 'compose', 'up', '-d', '--force-recreate', 'api'], check=True)
    deadline = time.monotonic() + DEPLOY_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            with urlopen(api_url.rstrip('/') + '/health', timeout=5) as response:
                health = json.load(response)
            if health.get('status') == 'ok' and str(health.get('version')) == champion:
                print(f'API พร้อมให้บริการ @champion v{champion}: {health}')
                return
        except (URLError, OSError, ValueError):
            pass  # container ยังเปิดไม่เสร็จ
        time.sleep(2)
    raise RuntimeError(f'API ที่ {api_url} ไม่ตอบ @champion v{champion} ภายใน {DEPLOY_TIMEOUT_S} วินาที')


@flow(name='delivery-eta-pipeline')
def pipeline(data: str = DATA_PATH, deploy_api: bool = False) -> int:
    # ลำดับการเรียกในฟังก์ชันนี้คือเส้นของ DAG: ขั้นถัดไปเริ่มได้เมื่อขั้นก่อนหน้าสำเร็จเท่านั้น
    if os.path.isdir(RAW_DIR):
        prepare_data()
    else:  # เช่นใน Docker image ที่ไม่มีข้อมูลดิบ -> ใช้ CSV ที่ commit ไว้
        print(f'WARN: ไม่พบ {RAW_DIR} ข้าม prepare_data ใช้ {DATA_PATH} เดิม')
    try:
        validate_data(data)
    except (SchemaError, SchemaErrors) as e:  # Errors = แปลงชนิดข้อมูลไม่ได้ (เช่น n_items="abc")
        print(f'STOP: ข้อมูลไม่ผ่าน validate ไม่เทรนต่อ\n{e}')
        return 2
    train()
    if not gate():
        print('STOP: gate ปฏิเสธโมเดลใหม่ (@champion ตัวเดิมยังใช้งานต่อ)')
        return 3
    if not deploy_api:
        print('DONE: โมเดลใหม่เป็น @champion แล้ว (ไม่ได้ใส่ --deploy: restart API เองเพื่อโหลดตัวใหม่)')
        return 0
    deploy(os.environ.get('API_URL', 'http://localhost:8000'))
    print('DONE: ข้อมูลดิบ -> ข้อมูลผ่าน -> เทรน -> ผ่าน gate -> API ให้บริการ @champion ตัวใหม่แล้ว')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default=DATA_PATH, help='CSV ที่จะตรวจด้วย schema ก่อนเทรน')
    parser.add_argument('--deploy', action='store_true', help='หลัง gate ผ่าน สร้าง API container ใหม่และรอจนใช้ @champion')
    args = parser.parse_args()
    sys.exit(pipeline(args.data, args.deploy))
