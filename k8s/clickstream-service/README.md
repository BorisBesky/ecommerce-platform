# Clickstream Service Manifests

Declarative manifests for deploying the clickstream analytics service (FastAPI backend + React UI) into the `ecommerce-platform` namespace.

## Components

- `clickstream-backend` – FastAPI service that exposes simulation controls, analytics APIs, and Ray orchestration
- `clickstream-frontend` – React dashboard served as a static site
- `clickstream-service-config` – ConfigMap containing shared configuration values (MinIO, Nessie, Ray endpoints)
- `clickstream-service-secrets` – Secret for sensitive credentials such as MinIO keys
- `clickstream-ingress` – Optional ingress for routing UI traffic and proxying `/api` requests to the backend

## Usage

1. Build the custom Docker images for the backend and frontend:
   ```bash
   make build-images
   ```
2. Push the custom Docker images to the local registry:
   ```bash
   make push-images-local
   ```
3. Update the container image references in the deployments to point at your registry (see `backend-deployment.yaml` and `frontend-deployment.yaml`).
4. Adjust secret values in `secret.yaml` for production environments.
5. (Optional) Change the ingress host (`clickstream.local`) or add TLS configuration to match your cluster ingress controller.  Apply manifests with Kustomize:
```bash
kubectl apply -k k8s/clickstream-service
```

## Integrating with existing overlays

Add `../clickstream-service` to the `resources` section in the overlay you use (`k8s/overlays/local`, `k8s/overlays/ghcr`, etc.) so the clickstream workloads are deployed alongside the core platform services.

## Environment Variables

The backend expects the following environment variables:

- `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`
- `ICEBERG_NAMESPACE`, `ICEBERG_WAREHOUSE`, `NESSIE_URI`, `NESSIE_BRANCH`
- `RAY_ADDRESS`, `RAY_NAMESPACE`, `RAY_JOB_SUBMISSION_URL`
- `DEFAULT_SIMULATION_BATCH_SIZE`, `DEFAULT_SIMULATION_USERS`

The frontend container should honour `API_BASE_URL` at runtime (e.g. through an entrypoint script) to ensure API calls are directed to the cluster service (`http://clickstream-backend:8000/api/v1`).

