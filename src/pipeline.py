"""DAG ของโปรเจกต์ด้วย Prefect:  validate_data -> train -> gate

รันจากโฟลเดอร์หลักของ repo:
  python src/pipeline.py                                  # ข้อมูลปกติ
  python src/pipeline.py --data demo_data/bad_orders.csv  # ข้อมูลเสีย -> หยุดที่ validate

Exit code (ตาม GUIDE สัญญา D):  0 = ทุกขั้นสำเร็จ,  2 = validate ไม่ผ่าน,  3 = gate ปฏิเสธโมเดล

เทียบกับ TFX ใน Lecture 11:
  validate_data = ExampleValidator (ใช้ Pandera schema ใน schema.py เป็น "สัญญา" ของข้อมูล)
  train         = Trainer          (train.py เทรนหลายโมเดล + log MLflow + ตั้ง @challenger)
  gate          = Evaluator+Pusher (registry.py promote: ผ่านเกณฑ์ = "blessed" -> @champion)
"""
import argparse
import os
import subprocess
import sys

from pandera.errors import SchemaError, SchemaErrors
from prefect import flow, task

from train import DATA_PATH, git_commit, load_splits


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
    print('DONE: โมเดลใหม่ผ่าน gate และเป็น @champion แล้ว (restart API เพื่อโหลดตัวใหม่)')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default=DATA_PATH, help='CSV ที่จะตรวจด้วย schema ก่อนเทรน')
    sys.exit(pipeline(parser.parse_args().data))
