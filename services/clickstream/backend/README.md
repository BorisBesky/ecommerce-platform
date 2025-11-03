# Clickstream Analytics Backend

Python FastAPI service that powers clickstream simulation controls, fraud detection analytics, recommendation accuracy visualization, and Ray job orchestration.

## Getting Started

```bash
cd services/clickstream/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Configuration

The service is configured through environment variables (leveraging `pydantic-settings`). Key variables:

- `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`
- `ICEBERG_NAMESPACE`, `ICEBERG_WAREHOUSE`, `NESSIE_URI`, `NESSIE_BRANCH`
- `RAY_ADDRESS`, `RAY_NAMESPACE`, `RAY_JOB_SUBMISSION_URL`
- `DEFAULT_SIMULATION_BATCH_SIZE`, `DEFAULT_SIMULATION_USERS`

Configure these via a `.env` file or injection in the deployment manifests. Sample values are aligned with the existing Kubernetes cluster services.

