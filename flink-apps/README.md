# Flink Applications

**NOTE**: These applications have been migrated to Kubernetes deployment.

For Kubernetes deployment, use the updated versions in `/k8s/flink-apps/` which include:
- Kubernetes-compatible service discovery
- Updated configuration for MinIO and Nessie services
- Sample data generation for testing

## Current Files

- `streaming-fraud-detection.py` - Original Docker Compose version
- `product-recommendation-fraud-detection.py` - Extended fraud detection
- `requirements.txt` - Python dependencies

## Migration

These applications are kept for reference but should not be used for new deployments. 
Use the Kubernetes platform instead:

```bash
cd k8s
./deploy-all.sh
./submit-sample-jobs.sh
```

See the main [README.md](../README.md) for complete deployment instructions.