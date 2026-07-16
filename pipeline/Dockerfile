FROM docker.io/python:3.12-slim

WORKDIR /pipeline
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY schema.sql .
COPY ingest ./ingest

# Le brut téléchargé est conservé dans un volume (voir docker-compose).
ENV PIPELINE_RAW_DIR=/pipeline/raw

ENTRYPOINT ["python", "-m", "ingest"]
