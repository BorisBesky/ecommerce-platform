# Spark Applications

**NOTE**: These applications have been migrated to Kubernetes deployment.

For Kubernetes deployment, use the updated versions in `/k8s/spark-apps/` which include:
- Kubernetes-compatible service discovery
- Updated configuration for MinIO and Nessie services
- Improved error handling and logging

## Current Files

- `batch_etl.py` - Original Docker Compose version
- `train_recommendation_model.py` - Original Docker version
- `train_recommendation_model_minio.py` - MinIO integration version

## Migration

These applications are kept for reference but should not be used for new deployments. 
Use the Kubernetes platform instead:

```bash
cd k8s
./deploy-all.sh
./submit-sample-jobs.sh
```

See the main [README.md](../README.md) for complete deployment instructions.