"""HTTP API for delivery time predictions."""

import os
from datetime import datetime
from pathlib import Path

import mlflow
import pandas as pd
import pandera.errors as pe
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from schema import input_schema

MODEL_NAME = 'delivery_eta'
PAGE_PATH = Path(__file__).resolve().parent / 'index.html'
app = FastAPI(title='Olist delivery prediction API')
model = None
model_version = None


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


@app.get('/', response_class=HTMLResponse, include_in_schema=False)
def home():
    return PAGE_PATH.read_text(encoding='utf-8')


@app.on_event('startup')
def load_model():
    # serve whatever the registry says is @champion; after promote/rollback, restart the API
    global model, model_version
    mlflow.set_tracking_uri(os.environ.get('MLFLOW_TRACKING_URI', 'sqlite:///mlflow.db'))
    try:
        model_version = mlflow.MlflowClient().get_model_version_by_alias(MODEL_NAME, 'champion').version
        model = mlflow.sklearn.load_model(f'models:/{MODEL_NAME}/{model_version}')
    except Exception as exc:  # no server / no champion yet -> /health reports it instead of crashing
        print(f'model not loaded: {exc}')


@app.get('/health')
def health():
    return {'status': 'ok' if model is not None else 'unavailable', 'model': MODEL_NAME, 'version': model_version}


@app.post('/predict')
def predict(order: Order):
    if model is None:
        raise HTTPException(status_code=503, detail='Model is unavailable')
    try:
        row = input_schema.validate(pd.DataFrame([order.model_dump(mode='json')]))
    except (pe.SchemaError, pe.SchemaErrors) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    days = max(0.0, float(model.predict(row)[0]))
    return {'predicted_delivery_days': days, 'model_version': model_version}
