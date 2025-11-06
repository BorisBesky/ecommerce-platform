FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/clickstream/backend/requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY services/clickstream/backend/app ./app
COPY tools/generate_data.py ./tools/generate_data.py

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

