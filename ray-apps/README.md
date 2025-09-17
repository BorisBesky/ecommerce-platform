# Ray Applications

**NOTE**: These applications have been migrated to Kubernetes deployment.

For Kubernetes deployment, use the updated versions in `/k8s/ray-apps/` which include:
- Kubernetes-compatible service discovery
- Updated configuration for MinIO services
- Improved Ray cluster integration

## Current Files

- `train_model.py` - Original Docker Compose version
- `train_recommendation_model.py` - Basic recommendation training
- `train_recommendation_model_k8s.py` - Kubernetes-compatible version
- `train_recommendation_model_minio.py` - MinIO integration version
- `requirements.txt` - Python dependencies

## Migration

These applications are kept for reference but should not be used for new deployments. 
Use the Kubernetes platform instead:

```bash
cd k8s
./deploy-all.sh
# Ray jobs are deployed via RayJob CRD
kubectl get rayjob -n ecommerce-platform
```

See the main [README.md](../README.md) for complete deployment instructions.