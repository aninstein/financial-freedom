FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data CONTAINER_RUNTIME=true \
    PATH=/app/runtime/.venv/bin:$PATH
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && \
    rm -rf /var/lib/apt/lists/*
RUN python -m venv /app/runtime/.venv
COPY requirements.txt ./
COPY vendor/deerflow ./vendor/deerflow
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt \
      vendor/deerflow/deerflow-extension-api-e9074b7.tar.gz \
      vendor/deerflow/deerflow-harness-e9074b7.tar.gz \
      'langchain-ollama>=1.0,<2.0'

COPY app ./app
COPY prototype ./prototype
COPY scripts ./scripts
ARG FINCH_UID=1000
RUN mkdir -p /app/data /app/runtime && touch /app/runtime/.ready && \
    useradd --create-home --uid ${FINCH_UID} finch && chown finch:finch /app/data
USER finch
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
