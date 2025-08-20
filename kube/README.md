# Ray Kubernetes Recommendation Training Setup

This directory contains the configuration and scripts needed to run the recommendation model training job on Ray Kubernetes.

## Files Overview

- `ray-job.recommendations-training.yaml` - RayJob configuration for Kubernetes
- `deploy-recommendations-k8s.sh` - Script to deploy the training job (Kubernetes-compatible)
- `deploy-recommendations-training.sh` - Original deployment script (for environments with shared filesystems)
- `prepare-data.py` - Script to prepare clickstream data for training
- `validate-config.sh` - Script to validate configuration and prerequisites
- `ray-job.pytorch-mnist.yaml` - Original PyTorch MNIST example (reference)

## Prerequisites

1. **Kubernetes cluster** with KubeRay operator installed
2. **kubectl** configured to access your cluster
3. **Ray training script** in `../ray-apps/train_recommendation_model_k8s.py`
4. **Docker Desktop Kubernetes** or similar local setup

## Quick Start

### 1. Install KubeRay Operator (if not already installed)

```bash
# Add the KubeRay Helm repository
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm repo update

# Install KubeRay operator
helm install kuberay-operator kuberay/kuberay-operator --version 1.0.0

# Verify installation
kubectl get pods -l app.kubernetes.io/name=kuberay-operator
```

### 2. Deploy the Training Job (Kubernetes-compatible)

```bash
# Deploy using the Kubernetes-compatible script
./deploy-recommendations-k8s.sh
```

This approach:

- Uses ConfigMaps to deploy the training script (no filesystem sharing needed)
- Generates sample data for training (works in any Kubernetes environment)
- Handles Docker Desktop Kubernetes limitations automatically

### 4. Monitor the Job

```bash
# Check job status
kubectl get rayjob rayjob-recommendations-training

# View detailed status
kubectl describe rayjob rayjob-recommendations-training

# View job logs (find job runner pod first)
kubectl get pods | grep rayjob-recommendations-training
kubectl logs <job-runner-pod-name>

# View Ray dashboard (if cluster is running)
kubectl port-forward service/rayjob-recommendations-training-*-head-svc 8265:8265
# Then open: http://localhost:8265
```

## Configuration Details

### RayJob Configuration

The `ray-job.recommendations-training.yaml` file is configured with:

- **Entry point**: `/apps/train_recommendation_model.py`
- **Dependencies**: numpy, pandas, boto3, s3fs
- **Environment variables**: Ray connection and MinIO configuration
- **Volume mounts**:
  - `/apps` → Ray training applications
  - `/data` → Training data (clickstream files)
- **Resource allocation**:
  - Head node: 1-2 CPU, 4-8Gi memory
  - Worker nodes: 1-2 CPU, 3-6Gi memory
  - 2 workers (scalable 1-3)

### Data Flow

1. **Input**: Clickstream data from `/data/clickstream.json`
2. **Processing**: Feature engineering (event weights, user-item ratings)
3. **Training**: FunkSVD collaborative filtering model
4. **Output**: Trained model saved to MinIO at `warehouse/models/recommendation_model.pkl`

### Training Algorithm

The job uses a custom FunkSVD (Funk Singular Value Decomposition) implementation:

- **Factors**: 20 latent factors
- **Epochs**: 10 training epochs
- **Learning rate**: 0.01
- **Regularization**: 0.02
- **Event weights**: view(1.0), add_to_cart(3.0), purchase(5.0), payment_failed(-2.0)

## Troubleshooting

### Common Issues

1. **"No clickstream files found"**

   ```bash
   # Check if data files exist
   ls -la ../data/clickstream-*.json
   # Run data preparation
   ./prepare-data.py
   ```

2. **"KubeRay operator not found"**

   ```bash
   # Install KubeRay operator
   helm repo add kuberay https://ray-project.github.io/kuberay-helm/
   helm install kuberay-operator kuberay/kuberay-operator --version 1.0.0
   ```

3. **"Volume mount failed"**
   - Ensure the hostPath volumes point to correct local directories
   - For production, consider using PersistentVolumes instead of hostPath

4. **"MinIO connection failed"**
   - Verify MinIO service is running: `kubectl get svc minio`
   - Check MinIO accessibility from within the cluster
   - The model will save locally if MinIO is unavailable

### Viewing Logs

```bash
# Get all pods for the training job
kubectl get pods -l ray.io/cluster=rayjob-recommendations-training-raycluster

# View logs from head node
kubectl logs rayjob-recommendations-training-raycluster-head-xxxxx

# View logs from worker nodes
kubectl logs rayjob-recommendations-training-raycluster-worker-xxxxx
```

### Resource Adjustments

To modify resource allocation, edit the `resources` sections in the YAML file:

```yaml
resources:
  limits:
    cpu: "4"      # Increase for faster training
    memory: "16Gi" # Increase for larger datasets
  requests:
    cpu: "2"
    memory: "8Gi"
```

## Cleanup

```bash
# Delete the training job
kubectl delete rayjob rayjob-recommendations-training

# Remove merged data file (optional)
rm ../data/clickstream.json
```

## Next Steps

After successful training:

1. **Verify model**: Check MinIO for `warehouse/models/recommendation_model.pkl`
2. **Deploy inference**: Use the trained model in your recommendation service
3. **Schedule retraining**: Set up CronJob for periodic model updates
4. **Monitor performance**: Track model accuracy and recommendation quality

## Production Considerations

For production deployment:

1. **Use PersistentVolumes** instead of hostPath for data
2. **Configure resource limits** based on your data size
3. **Set up monitoring** with Prometheus/Grafana
4. **Implement model versioning** in your MLflow or similar system
5. **Add data validation** before training
6. **Configure autoscaling** for worker nodes
7. **Use secrets** for MinIO credentials instead of plain text
