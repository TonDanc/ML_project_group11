"""HTTP API for delivery time predictions."""

import logging
import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import pandera.errors as pe
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from alerts import notify_validation_failure
from schema import input_schema


MODEL_NAME = 'delivery_eta'
PAGE_PATH = Path(__file__).resolve().parent / 'index.html'

app = FastAPI(title='Olist delivery prediction API')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
logger.propagate = False

model = None
model_version = None

started_at = time.perf_counter()
# Keep the latest 1,000 /predict latencies in memory.
latencies_ms = deque(maxlen=1000)
# Cumulative counters since this process started.
requests_total = 0
errors_total = 0
rejected_total = 0


class Order(BaseModel):
    customer_state: str
    seller_state: str
    customer_lat: float
    customer_lng: float
    seller_lat: float
    seller_lng: float
    n_sellers: int
    n_items: int
    total_price: float
    total_freight: float
    total_weight_g: float
    estimated_delivery_days: int
    order_purchase_timestamp: datetime


@app.middleware('http')
async def record_predict_metrics(request: Request, call_next):
    # This also catches requests rejected by Pydantic before predict().
    global requests_total, errors_total, rejected_total

    if request.url.path != '/predict':
        return await call_next(request)

    start = time.perf_counter()
    requests_total += 1

    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        latencies_ms.append(latency_ms)

        if 400 <= status_code < 500:
            rejected_total += 1
            result = 'rejected'
        elif status_code >= 500:
            errors_total += 1
            result = 'error'
        else:
            result = 'ok'

        logger.info(
            '%s result=%s latency_ms=%.3f model_version=%s',
            datetime.now().astimezone().isoformat(timespec='milliseconds'),
            result,
            latency_ms,
            model_version,
        )


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError
):
    payload = exc.body if isinstance(exc.body, dict) else None

    notify_validation_failure(str(exc), payload)

    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({'detail': exc.errors()}),
    )


@app.get('/', response_class=HTMLResponse, include_in_schema=False)
def home():
    return PAGE_PATH.read_text(encoding='utf-8')


@app.on_event('startup')
def load_model():
    # serve whatever the registry says is @champion;
    global model, model_version

    mlflow.set_tracking_uri(
        os.environ.get('MLFLOW_TRACKING_URI', 'sqlite:///mlflow.db')
    )

    try:
        model_version = (
            mlflow.MlflowClient()
            .get_model_version_by_alias(MODEL_NAME, 'champion')
            .version
        )
        model = mlflow.sklearn.load_model(
            f'models:/{MODEL_NAME}/{model_version}'
        )
    except Exception as exc:
        print(f'model not loaded: {exc}')


@app.get('/health')
def health():
    return {
        'status': 'ok' if model is not None else 'unavailable',
        'model': MODEL_NAME,
        'version': model_version,
    }


@app.get('/metrics')
async def metrics():
    values = list(latencies_ms)

    if values:
        p50, p95 = np.percentile(values, [50, 95])
    else:
        p50 = p95 = 0.0

    return {
        'requests_total': requests_total,
        'errors_total': errors_total,
        'rejected_total': rejected_total,
        'latency_ms': {
            'p50': float(p50),
            'p95': float(p95),
            'count': len(values),
        },
        'model_version': model_version,
        'uptime_s': time.perf_counter() - started_at,
    }


@app.post('/predict')
def predict(order: Order):
    payload = order.model_dump(mode='json')

    try:
        row = input_schema.validate(
            pd.DataFrame([payload])
        )
    except (pe.SchemaError, pe.SchemaErrors) as exc:
        notify_validation_failure(str(exc), payload)

        raise HTTPException(
            status_code=422,
            detail=str(exc)
        ) from exc

    if model is None:
        raise HTTPException(status_code=503, detail='Model is unavailable')

    days = max(
        0.0,
        float(model.predict(row)[0])
    )

    return {
        'predicted_delivery_days': days,
        'model_version': model_version
    }
