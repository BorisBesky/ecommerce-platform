# Distributed Training with Ray

## Overview

The recommendation model training has been enhanced to distribute the training workload across 2 Ray worker nodes. This improves training performance by parallelizing the gradient computation.

## What Changed

### 1. Training Script (`train_recommendation_model_k8s.py`)

#### New Remote Function
- Added `@ray.remote` decorated function `train_chunk_remote()` that processes a chunk of training data on a worker node
- Each worker computes gradients for its assigned data chunk independently
- Workers log their hostname to show which node is processing each chunk

#### New Distributed Training Method
- Added `fit_distributed()` method to the `FunkSVD` class
- Splits training data into chunks (one per worker)
- Distributes chunks across Ray workers using `ray.remote()`
- Aggregates gradients from all workers after each epoch
- Automatically detects available Ray workers and adjusts accordingly

#### Updated Main Function
- Changed from `model.fit()` to `model.fit_distributed()`
- Auto-detects number of available CPUs in the Ray cluster
- Defaults to 2 workers as configured in `ray.yaml`

### 2. Ray Cluster Configuration (`ray.yaml`)

The cluster is already configured with 2 worker nodes:
- **Worker replicas**: 2 (can scale 1-3)
- **Worker resources**: 1-2 CPUs, 1-2 GB memory each
- **Head node resources**: 1-2 CPUs, 2-4 GB memory

## How It Works

### Training Flow

1. **Data Loading** (Distributed with Ray Data)
   - **Ray Data distributes reading** clickstream JSON from MinIO across workers
   - **Workers transform data in parallel** (add ratings based on event types)
   - **Distributed processing** of feature engineering
   - Head node aggregates results into final ratings DataFrame
   - Splits into train/test sets

2. **Model Initialization** (Head Node)
   - Initializes user and item factor matrices
   - Prepares training data arrays

3. **Distributed Training Loop** (Per Epoch)
   - Head node splits training data into N chunks (N = number of workers)
   - Each chunk is sent to a Ray worker via `train_chunk_remote.remote()`
   - Workers process chunks **in parallel**:
     - Compute predictions
     - Calculate errors
     - Compute gradient updates
   - Head node waits for all workers to complete
   - Head node aggregates gradients from all workers
   - Head node updates the model parameters

4. **Model Saving** (Head Node)
   - Saves trained model to MinIO

### Parallelization Benefits

#### Data Loading & Processing
- **Before**: Head node loads all data from MinIO sequentially
- **After (Ray Data)**: Workers load and transform data in parallel
- **Benefit**: Faster data ingestion, reduced head node bottleneck

#### Model Training
- **Before**: Sequential processing of all training samples on a single node
- **After**: Parallel processing of training samples across 2 worker nodes
- **Expected speedup**: ~1.8-2.2x (including distributed data loading)

### Ray Data Advantages

1. **Distributed I/O**: Multiple workers read from MinIO simultaneously
2. **Parallel Transformations**: Feature engineering runs on all workers
3. **Memory Efficiency**: Data is processed in batches across workers
4. **Automatic Scaling**: Ray Data automatically adapts to available workers

## Verification

### Check Worker Distribution

When the training job runs, you should see log messages like:

```
Loading training data with Ray Data (distributed across workers)...
Reading data from s3://warehouse/data/clickstream.json (distributed load across workers)...
[Ray Data Worker on rayjob-...-worker-xxxxx] Processing 5234 records...
[Ray Data Worker on rayjob-...-worker-yyyyy] Processing 5189 records...
Loaded 10423 clickstream records using Ray Data.
Transforming data (distributed processing across workers)...
Created 2456 user-item ratings from clickstream data.

Starting distributed training with 2 workers...
Ray cluster has 6.0 CPUs available. Using 2 workers for training.
[Worker 0 on rayjob-recommendations-training-worker-xxxxx] Processing 1228 training samples...
[Worker 1 on rayjob-recommendations-training-worker-yyyyy] Processing 1228 training samples...
[Worker 0 on rayjob-recommendations-training-worker-xxxxx] Completed processing. SE: 12345.67
[Worker 1 on rayjob-recommendations-training-worker-yyyyy] Completed processing. SE: 12389.45
Epoch 1/10 - RMSE: 2.3456 (distributed across 2 workers)
```

The different hostnames confirm that:
1. **Ray Data is distributing data loading** across worker nodes
2. **Training is distributed** across worker nodes

### Monitor Ray Dashboard

1. Port-forward the Ray dashboard:
   ```bash
   kubectl port-forward -n ecommerce-platform svc/rayjob-recommendations-training-head-svc 8265:8265
   ```

2. Open http://localhost:8265 in your browser

3. Navigate to the "Tasks" tab to see:
   - Multiple `train_chunk_remote` tasks running in parallel
   - Task distribution across different worker nodes
   - CPU utilization across the cluster

### Check Pod Status

```bash
# List all Ray pods
kubectl get pods -n ecommerce-platform -l app=ray

# You should see:
# - 1 head pod
# - 2 worker pods
# - 1 job submitter pod

# Check logs from a worker pod
kubectl logs -n ecommerce-platform rayjob-recommendations-training-worker-<tab-complete>
```

## Scaling Considerations

### Increasing Workers

To use more workers (e.g., 4 workers):

1. Update `ray.yaml`:
   ```yaml
   workerGroupSpecs:
   - replicas: 4  # Change from 2 to 4
     minReplicas: 1
     maxReplicas: 5  # Increase max if needed
   ```

2. The training script will automatically detect and use all available workers

### Performance Trade-offs

- **More workers**: Faster per-epoch training, but higher aggregation overhead
- **Optimal range**: 2-4 workers for typical dataset sizes
- **Diminishing returns**: Beyond 4-6 workers, communication overhead may exceed benefits

## Technical Details

### Gradient Aggregation Strategy

The implementation uses a **data-parallel** approach:
- Each worker has a complete copy of the model (user_factors, item_factors)
- Workers compute gradients independently on their data chunks
- Head node averages gradients from all workers
- Head node applies averaged gradients to update the model

This is suitable for SGD-based collaborative filtering where:
- Model size is relatively small (can fit in memory of each worker)
- Gradient computation is the bottleneck
- Communication overhead is acceptable

### Why Not Full Distributed SGD?

Traditional distributed SGD with parameter servers was not used because:
1. **Model size**: Factor matrices are small enough to copy to workers
2. **Simplicity**: Aggregated gradient approach is simpler to implement
3. **Convergence**: This approach maintains similar convergence properties to single-node training

## Troubleshooting

### Workers Not Being Used

If you see "Using 1 workers" in the logs:
1. Check Ray cluster status: `kubectl get raycluster -n ecommerce-platform`
2. Verify worker pods are running: `kubectl get pods -n ecommerce-platform -l component=worker`
3. Check Ray dashboard for connected nodes

### Out of Memory Errors

If workers run out of memory:
1. Reduce `n_factors` in the model (currently 20)
2. Increase worker memory in `ray.yaml`
3. Process smaller data chunks

### Slow Training

If distributed training is slower than single-node:
1. Dataset might be too small (overhead dominates)
2. Network latency between nodes
3. Consider reducing number of workers for small datasets

