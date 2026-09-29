"""HTTP API for delivery time predictions."""

import __main__
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
import pandera.errors as pe
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from schema import input_schema
from train import add_features

__main__.add_features = add_features

MODEL_PATH = Path(__file__).resolve().parents[1] / 'models' / 'model.joblib'

app = FastAPI(title='Olist delivery prediction API')
model = None


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


@app.on_event('startup')
def load_model():
    global model
    model = joblib.load(MODEL_PATH)


@app.get('/health')
def health():
    return {'status': 'ok' if model is not None else 'unavailable'}


@app.post('/predict')
def predict(order: Order):
    if model is None:
        raise HTTPException(status_code=503, detail='Model is unavailable')

    try:
        row = input_schema.validate(
            pd.DataFrame([order.model_dump(mode='json')])
        )
    except (pe.SchemaError, pe.SchemaErrors) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    days = max(0.0, float(model.predict(row)[0]))
    return {'predicted_delivery_days': days}