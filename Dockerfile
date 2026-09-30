FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

COPY ["cleaned_data/feature extraction/shipping_distance_duration.csv", "cleaned_data/feature extraction/shipping_distance_duration.csv"]

# no training at build time: the model comes from the MLflow registry (@champion), see docker-compose.yml

EXPOSE 8000

CMD ["uvicorn", "api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
