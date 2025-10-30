# Migration Guide: Docker Compose to Kubernetes

This guide helps you migrate from the legacy Docker Compose deployment to the new Kubernetes-based platform.

## Overview

The platform has been completely migrated from Docker Compose to Kubernetes for better:
- **Scalability**: Auto-scaling and resource management
- **Reliability**: Health checks and self-healing
- **Production readiness**: Security, monitoring, and observability
- **Cloud compatibility**: Works on any Kubernetes cluster

## What Changed

### Deployment Architecture

| Component | Old (Docker Compose) | New (Kubernetes) |
|-----------|---------------------|------------------|
| **Deployment** | `docker-compose up` | `./k8s/deploy-all.sh` |
| **Service Discovery** | Container names | Kubernetes DNS |
| **Storage** | Host volumes | Persistent Volume Claims |
| **Networking** | Docker networks | Kubernetes services |
| **Scaling** | Manual | Auto-scaling |
| **Monitoring** | Docker logs | Health checks + metrics |

### File Structure Changes

```
# OLD structure
├── docker/
│   ├── docker-compose.yml
│   ├── Dockerfile.spark
│   └── Dockerfile.flink
├── spark-apps/submit_batch_etl.sh
└── flink-apps/submit-flink-job.sh

# NEW structure
├── k8s/                    # New Kubernetes deployment
│   ├── deploy-all.sh      # Replaces docker-compose up
│   ├── *.yaml             # Kubernetes manifests
│   └── */                 # Updated applications
└── legacy/                # Old files moved here
```

## Migration Steps

### 1. Stop Existing Docker Deployment

If you have the old Docker Compose deployment running:

```bash
# Stop all containers
cd legacy/docker  # (old docker/ directory)
docker-compose down -v

# Clean up volumes (optional - removes all data)
docker volume prune
```

### 2. Prepare Kubernetes Environment

Ensure you have a Kubernetes cluster ready:

```bash
# Check prerequisites
cd k8s
./check-prerequisites.sh
```

### 3. Deploy to Kubernetes

```bash
# Deploy the complete platform
./deploy-all.sh

# Validate deployment
./validate-deployment.sh

# Test with sample jobs
./submit-sample-jobs.sh
```

### 4. Data Migration (Optional)

If you had data in the old Docker volumes:

```bash
# Export data from old MinIO (if still accessible)
docker run --rm -v old_minio_data:/data -v $(pwd):/backup alpine tar czf /backup/minio_backup.tar.gz /data

# Access new MinIO and restore
kubectl port-forward svc/minio 9001:9001 -n ecommerce-platform
# Use MinIO console to upload data
```

## Application Changes

### Spark Applications

| Aspect | Old | New |
|--------|-----|-----|
| **Submission** | `docker-compose exec` | `kubectl run` |
| **Service URLs** | `http://nessie:19120` | `http://nessie.ecommerce-platform.svc.cluster.local:19120` |
| **Files** | `batch_etl.py` | `batch_etl_k8s.py` |

### Flink Applications

| Aspect | Old | New |
|--------|-----|-----|
| **Submission** | `docker-compose exec` | `kubectl exec` |
| **Configuration** | Docker environment | Kubernetes ConfigMap |
| **Files** | `streaming-fraud-detection.py` | `streaming_fraud_detection_k8s.py` |

### Ray Applications

| Aspect | Old | New |
|--------|-----|-----|
| **Deployment** | Direct container | RayJob CRD |
| **Scaling** | Fixed workers | Auto-scaling |
| **Files** | `train_model.py` | `train_recommendation_model_k8s.py` |

## Configuration Updates

### Service Discovery

```python
# OLD (Docker Compose)
NESSIE_URI = "http://nessie:19120/api/v1"
MINIO_ENDPOINT = "http://minio:9000"

# NEW (Kubernetes)
NESSIE_URI = "http://nessie.ecommerce-platform.svc.cluster.local:19120/api/v1"
MINIO_ENDPOINT = "http://minio.ecommerce-platform.svc.cluster.local:9000"
```

### Resource Limits

Kubernetes provides better resource management:

```yaml
# Example: Spark worker resources
resources:
  requests:
    cpu: 1000m
    memory: 2Gi
  limits:
    cpu: 2000m
    memory: 3Gi
```

## Monitoring and Access

### Old Way (Docker Compose)

```bash
# Access services directly
curl http://localhost:8080  # Spark UI
curl http://localhost:8081  # Flink UI
curl http://localhost:9001  # MinIO Console
```

### New Way (Kubernetes)

```bash
# Port forward to access services
kubectl port-forward svc/spark-master 8080:8080 -n ecommerce-platform
kubectl port-forward svc/flink-jobmanager 8081:8081 -n ecommerce-platform
kubectl port-forward svc/minio 9001:9001 -n ecommerce-platform
```

## Troubleshooting Migration

### Common Issues

1. **Service connectivity errors**
   ```bash
   # Check service status
   kubectl get pods -n ecommerce-platform
   kubectl get services -n ecommerce-platform
   ```

2. **Resource constraints**
   ```bash
   # Check resource usage
   kubectl top pods -n ecommerce-platform
   kubectl describe nodes
   ```

3. **Storage issues**
   ```bash
   # Check persistent volumes
   kubectl get pv,pvc -n ecommerce-platform
   ```

### Getting Help

- **Validation**: Use `./validate-deployment.sh` to check platform health
- **Logs**: `kubectl logs -l app=<service> -n ecommerce-platform`
- **Events**: `kubectl get events -n ecommerce-platform --sort-by='.lastTimestamp'`
- **Documentation**: See main [README.md](../README.md) for comprehensive guide

## Benefits of Migration

✅ **Better Resource Management**: CPU and memory limits, requests
✅ **Auto-scaling**: Horizontal and vertical pod autoscaling
✅ **Health Monitoring**: Liveness and readiness probes
✅ **Service Discovery**: DNS-based service discovery
✅ **Security**: Network policies, RBAC, secrets management
✅ **Cloud Ready**: Works on any Kubernetes cluster (EKS, GKE, AKS)
✅ **Production Ready**: High availability, fault tolerance

## Rollback Plan

If you need to temporarily rollback to Docker Compose:

```bash
# The old files are preserved in legacy/
cd legacy/docker
docker-compose up -d

# Update applications to use old service names
# (restore from git history if needed)
```

However, we recommend fixing any Kubernetes issues instead of rolling back, as the Kubernetes deployment provides much better production capabilities.

## Next Steps

After successful migration:

1. **Configure monitoring** with Prometheus/Grafana
2. **Set up ingress** for external access
3. **Enable autoscaling** based on your workload
4. **Implement backup strategies** for data
5. **Configure CI/CD** for application deployments

For production deployments, see the [Production Deployment](../README.md#-production-deployment) section in the main README.