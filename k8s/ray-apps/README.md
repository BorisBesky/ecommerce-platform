# Ray Applications

This directory contains Ray applications for distributed machine learning workloads in the e-commerce platform.

## Contents

### Training Scripts

- **`train_recommendation_model_k8s.py`** - Main recommendation model training script with distributed training support
  - Uses FunkSVD collaborative filtering algorithm
  - **Ray Data**: Distributed data loading from MinIO across workers
  - **Distributed Training**: Training parallelized across multiple Ray worker nodes
  - **Feature Engineering**: Parallel transformation on worker nodes
  - Saves trained model to MinIO
  - See [DISTRIBUTED_TRAINING.md](DISTRIBUTED_TRAINING.md) for details

### Utilities

- **`verify_distributed_setup.py`** - Verification script to check Ray cluster configuration
  - Tests cluster connectivity
  - Validates node distribution
  - Reports resource availability
  - Verifies remote task execution

### Documentation

- **`DISTRIBUTED_TRAINING.md`** - Comprehensive guide to distributed training
  - Architecture overview
  - How it works
  - Verification steps
  - Troubleshooting guide
  - Scaling considerations

### Configuration

- **`requirements.txt`** - Python dependencies for Ray applications
  - numpy, pandas - Data processing
  - boto3, s3fs - MinIO/S3 access
  - ray[train] - Distributed computing

## Quick Start

### 1. Deploy Ray Cluster

From the project root:
```bash
kubectl apply -f k8s/ray.yaml
```

### 2. Verify Cluster Setup

```bash
# Check pods are running
kubectl get pods -n ecommerce-platform -l app=ray

# Expected: 1 head + 2 workers
```

### 3. Monitor Training

```bash
# Get head pod name
kubectl get pods -n ecommerce-platform -l ray.io/node-type=head

# View logs
kubectl logs -n ecommerce-platform <head-pod-name> -f
```

### 4. Access Ray Dashboard

```bash
kubectl port-forward -n ecommerce-platform \
  svc/rayjob-recommendations-training-head-svc 8265:8265
```

Open http://localhost:8265

## Distributed Training

The recommendation model training is distributed across 2 Ray worker nodes by default.

### How It Works

1. **Distributed Data Loading (Ray Data)** - Workers load clickstream data from MinIO in parallel
2. **Parallel Feature Engineering (Ray Data)** - Workers transform data (event types → ratings) in parallel
3. **Data Splitting** - Training data split into chunks (one per worker)
4. **Parallel Training** - Each worker computes gradients for its chunk
5. **Gradient Aggregation** - Head node aggregates and applies gradients
6. **Model Saving** - Trained model saved to MinIO

### Performance

- **Workers**: 2 (configurable)
- **Expected Speedup**: ~1.8-2.2x vs single-node (including Ray Data benefits)
- **Data Loading**: Parallelized across workers (Ray Data)
- **Training**: Parallelized gradient computation
- **Scalability**: Can scale to 3+ workers

See [DISTRIBUTED_TRAINING.md](DISTRIBUTED_TRAINING.md) for detailed information.

## Development

### Local Testing

To test the training script locally (without Kubernetes):

```bash
# Start Ray locally
ray start --head --port=6379

# Set environment variables
export RAY_ADDRESS="127.0.0.1:6379"
export MINIO_ENDPOINT="http://localhost:9000"
export MINIO_ACCESS_KEY="minioadmin"
export MINIO_SECRET_KEY="minioadmin"

# Run training
python train_recommendation_model_k8s.py

# Stop Ray
ray stop
```

### Adding New Ray Applications

1. Create Python script in this directory
2. Add dependencies to `requirements.txt`
3. Update `ray.yaml` entrypoint if needed
4. Create ConfigMap: `kubectl create configmap <name> --from-file=<script.py>`
5. Deploy via `ray.yaml`

### Deploy modified training script
```bash
kubectl create configmap ray-training-script \
  --from-file=k8s/ray-apps/train_recommendation_model_k8s.py \
  -n ecommerce-platform \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Redeploy Ray cluster
```bash
kubectl apply -f k8s/ray.yaml
```

## Configuration

### Ray Cluster Settings

Edit `k8s/ray.yaml`:

```yaml
workerGroupSpecs:
- replicas: 2  # Number of worker nodes
  minReplicas: 1
  maxReplicas: 3
  resources:
    cpu: "2"     # CPUs per worker
    memory: "2Gi" # Memory per worker
```

### Training Parameters

Edit `train_recommendation_model_k8s.py`:

```python
model = FunkSVD(
    n_factors=20,   # Latent factors
    n_epochs=10,    # Training epochs
    lr=0.01,        # Learning rate
    reg=0.02        # Regularization
)
```

## Troubleshooting

### Workers Not Running

```bash
# Check worker status
kubectl get pods -n ecommerce-platform -l component=worker

# Describe worker issues
kubectl describe pods -n ecommerce-platform -l component=worker

# Check Ray cluster status
kubectl describe raycluster -n ecommerce-platform
```

### Training Fails

```bash
# Check head node logs
kubectl logs -n ecommerce-platform -l ray.io/node-type=head

# Check worker logs
kubectl logs -n ecommerce-platform -l component=worker

# Verify MinIO connectivity
kubectl exec -n ecommerce-platform <head-pod> -- \
  curl -I http://minio:9000
```

### Out of Memory

Increase worker memory in `k8s/ray.yaml`:
```yaml
resources:
  limits:
    memory: "4Gi"  # Increase as needed
```

## Architecture

```
           ┌──────────┐
           │  MinIO   │
           │ - Data   │
           │ - Model  │
           └──────────┘
                 │
        ┌────────┴────────┐
        │  Ray Data I/O   │ (Distributed Read)
        └────────┬────────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
    ┌──────────┐    ┌──────────┐
    │ Worker 1 │    │ Worker 2 │
    │ - Load   │    │ - Load   │
    │   Data   │    │   Data   │
    │ - Trans- │    │ - Trans- │
    │   form   │    │   form   │
    │ - Train  │    │ - Train  │
    │   Chunk  │    │   Chunk  │
    └──────────┘    └──────────┘
        │                 │
        └────────┬────────┘
                 ▼
    ┌──────────────────────────┐
    │    Ray Head Node         │
    │  - Job coordination      │
    │  - Gradient aggregation  │
    │  - Model updates         │
    │  - Model persistence     │
    └──────────────────────────┘
```

## Resources

- [Ray Documentation](https://docs.ray.io/)
- [Ray on Kubernetes](https://docs.ray.io/en/latest/cluster/kubernetes/index.html)
- [Ray Train](https://docs.ray.io/en/latest/train/train.html)
- [Distributed Training Guide](DISTRIBUTED_TRAINING.md)

## Next Steps

1. ✅ Implement distributed training across 2 nodes
2. ✅ Implement Ray Data for distributed data loading and preprocessing
3. 🔄 Add GPU support for deep learning models
4. 🔄 Add Ray Tune for hyperparameter optimization
5. 🔄 Implement Ray Serve for model serving

