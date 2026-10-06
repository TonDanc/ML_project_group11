FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

COPY ["cleaned_data/feature extraction/shipping_distance_duration.csv", "cleaned_data/feature extraction/shipping_distance_duration.csv"]

# no training at build time: the model comes from the MLflow registry (@champion), see docker-compose.yml

EXPOSE 8000

# 8 worker processes: 1 worker caps at ~22 req/s (~45 ms CPU per request); tune to the host's CPU count, see docs/serving.md
# OMP_NUM_THREADS=1 only for the API (train shares this image and wants all cores): otherwise every
# worker's HistGradientBoosting spawns one thread per CPU and they fight
CMD ["env", "OMP_NUM_THREADS=1", "uvicorn", "api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "--workers", "8"]
