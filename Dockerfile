FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

COPY ["cleaned_data/feature extraction/shipping_distance_duration.csv", "cleaned_data/feature extraction/shipping_distance_duration.csv"]

RUN python src/train.py && rm -rf cleaned_data

EXPOSE 8000

CMD ["uvicorn", "api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]