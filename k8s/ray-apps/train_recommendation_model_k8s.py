import os
import glob
import math
import pickle
from typing import Dict, Tuple, Optional, List
import warnings

import numpy as np
import pandas as pd
import ray
import boto3
from botocore.config import Config

# --- Configuration ---
# Ray connection address strategy:
# - If RAY_ADDRESS env var is set, use that (e.g., "ray://ray-head:10001" or "ray-head:6379" or "auto").
# - Otherwise, try a sensible sequence for in-cluster runs: auto -> tcp -> client.
RAY_ADDRESS = os.environ.get("RAY_ADDRESS")
# NOTE: We are not reading from Iceberg in this version to simplify the training logic,
# but the principle of loading data first remains the same.
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://minio.ecommerce-platform.svc.cluster.local:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
S3_BUCKET = os.environ.get("CLICKSTREAM_S3_BUCKET", "warehouse")
OUTPUT_MODEL_KEY = os.environ.get("MODEL_OUTPUT_KEY", "models/recommendation_model.pkl")
# Preferred key for clickstream json inside the bucket (staged by submit-sample-jobs or data upload)
CLICKSTREAM_S3_KEY = os.environ.get("CLICKSTREAM_S3_KEY", "data/clickstream.json")
CLICKSTREAM_LOCAL_FALLBACK = "/data/clickstream.json"  # fallback local path

# ------------------------
# Ray Remote Function for Distributed Training
# ------------------------
@ray.remote
def train_chunk_remote(ui: np.ndarray, ii: np.ndarray, rr: np.ndarray,
                       user_factors: np.ndarray, item_factors: np.ndarray,
                       lr: float, reg: float, chunk_id: int) -> Tuple[np.ndarray, np.ndarray, float, int]:
    """
    Train on a chunk of data and return gradient updates.
    
    Args:
        ui: User indices array
        ii: Item indices array
        rr: Ratings array
        user_factors: Current user factor matrix (read-only copy)
        item_factors: Current item factor matrix (read-only copy)
        lr: Learning rate
        reg: Regularization parameter
        chunk_id: Identifier for this chunk (for logging)
        
    Returns:
        Tuple of (user_updates, item_updates, squared_error_sum, num_samples)
    """
    import socket
    node_name = socket.gethostname()
    print(f"[Worker {chunk_id} on {node_name}] Processing {len(rr)} training samples...")
    
    # Create local copies to apply updates
    local_user_factors = user_factors.copy()
    local_item_factors = item_factors.copy()
    se = 0.0
    
    # Apply SGD updates locally
    for idx in range(len(rr)):
        u = ui[idx]
        i = ii[idx]
        r = rr[idx]
        pu = local_user_factors[u]
        qi = local_item_factors[i]
        pred = float(np.dot(pu, qi))
        err = r - pred
        
        # Clip error to keep updates stable (but allow larger errors for 1-5 scale)
        err = np.clip(err, -10.0, 10.0)
        se += err * err
        
        # Apply SGD updates directly
        local_user_factors[u] += lr * (err * qi - reg * pu)
        local_item_factors[i] += lr * (err * pu - reg * qi)
        
        # Clamp factors to prevent explosion (more relaxed bounds)
        local_user_factors[u] = np.clip(local_user_factors[u], -10.0, 10.0)
        local_item_factors[i] = np.clip(local_item_factors[i], -10.0, 10.0)
    
    print(f"[Worker {chunk_id} on {node_name}] Completed processing. SE: {se:.2f}")
    return local_user_factors, local_item_factors, se, len(rr)

# ------------------------
# Helper Functions
# ------------------------
def _BotoCfg(**kwargs):
    """Helper to create boto3 Config object"""
    return Config(**kwargs)

# ------------------------
# Simple FunkSVD (SGD) Recommender (pure NumPy)
# ------------------------
class FunkSVD:
    def __init__(self, n_factors=20, n_epochs=10, lr=0.005, reg=0.05, random_state=42, 
                 early_stopping=True, patience=3, min_delta=0.001):
        self.n_factors = n_factors
        self.n_epochs = n_epochs
        self.lr = lr
        self.reg = reg
        self.random_state = random_state
        self.early_stopping = early_stopping
        self.patience = patience
        self.min_delta = min_delta
        self.user_factors = None  # type: Optional[np.ndarray]
        self.item_factors = None  # type: Optional[np.ndarray]
        self.user_map = {}  # type: Dict
        self.item_map = {}  # type: Dict
        self.user_inv = {}  # type: Dict
        self.item_inv = {}  # type: Dict
        self.training_history = []  # type: List[float]

    def fit(self, df: pd.DataFrame) -> None:
        # df has columns: user_id, product_id, rating
        users = df['user_id'].unique().tolist()
        items = df['product_id'].unique().tolist()
        self.user_map = {u: i for i, u in enumerate(users)}
        self.item_map = {m: i for i, m in enumerate(items)}
        self.user_inv = {i: u for u, i in self.user_map.items()}
        self.item_inv = {i: m for m, i in self.item_map.items()}

        n_users = len(users)
        n_items = len(items)
        rng = np.random.default_rng(self.random_state)
        self.user_factors = 0.01 * rng.standard_normal((n_users, self.n_factors))
        self.item_factors = 0.01 * rng.standard_normal((n_items, self.n_factors))

        # Build training triples
        ui = df['user_id'].map(self.user_map).to_numpy()
        ii = df['product_id'].map(self.item_map).to_numpy()
        rr = df['rating'].astype(float).to_numpy()

        for epoch in range(self.n_epochs):
            # Shuffle indices each epoch
            order = rng.permutation(len(rr))
            se = 0.0
            for idx in order:
                u = ui[idx]
                i = ii[idx]
                r = rr[idx]
                pu = self.user_factors[u]
                qi = self.item_factors[i]
                pred = float(np.dot(pu, qi))
                err = r - pred
                # Clip error to keep updates stable
                err = np.clip(err, -10.0, 10.0)
                se += err * err
                # SGD updates
                self.user_factors[u] += self.lr * (err * qi - self.reg * pu)
                self.item_factors[i] += self.lr * (err * pu - self.reg * qi)
                # Clamp factor values to avoid explosion
                self.user_factors[u] = np.clip(self.user_factors[u], -10.0, 10.0)
                self.item_factors[i] = np.clip(self.item_factors[i], -10.0, 10.0)
            rmse = math.sqrt(se / max(len(rr), 1))
            print("Epoch {}/{} - RMSE: {:.4f}".format(epoch + 1, self.n_epochs, rmse))
    
    def fit_distributed(self, df: pd.DataFrame, num_workers: int = 2) -> None:
        """
        Distributed training across multiple Ray workers.
        Each worker processes a chunk of the data and computes gradients.
        The head node aggregates gradients and updates the model.
        """
        # Initialize model parameters
        users = df['user_id'].unique().tolist()
        items = df['product_id'].unique().tolist()
        self.user_map = {u: i for i, u in enumerate(users)}
        self.item_map = {m: i for i, m in enumerate(items)}
        self.user_inv = {i: u for u, i in self.user_map.items()}
        self.item_inv = {i: m for m, i in self.item_map.items()}

        n_users = len(users)
        n_items = len(items)
        rng = np.random.default_rng(self.random_state)
        self.user_factors = 0.01 * rng.standard_normal((n_users, self.n_factors))
        self.item_factors = 0.01 * rng.standard_normal((n_items, self.n_factors))

        # Build training triples
        ui = df['user_id'].map(self.user_map).to_numpy()
        ii = df['product_id'].map(self.item_map).to_numpy()
        rr = df['rating'].astype(float).to_numpy()

        print(f"Starting distributed training with {num_workers} workers...")
        
        best_rmse = float('inf')
        patience_counter = 0
        
        for epoch in range(self.n_epochs):
            # Shuffle indices each epoch
            order = rng.permutation(len(rr))
            
            # Split data into chunks for parallel processing
            chunk_size = len(order) // num_workers
            chunks = []
            for w in range(num_workers):
                start_idx = w * chunk_size
                end_idx = start_idx + chunk_size if w < num_workers - 1 else len(order)
                chunk_indices = order[start_idx:end_idx]
                chunks.append((ui[chunk_indices], ii[chunk_indices], rr[chunk_indices]))
            
            # Distribute training across workers
            gradient_futures = []
            for chunk_id, chunk in enumerate(chunks):
                future = train_chunk_remote.remote(
                    chunk[0], chunk[1], chunk[2],
                    self.user_factors.copy(), self.item_factors.copy(),
                    self.lr, self.reg, chunk_id
                )
                gradient_futures.append(future)
            
            # Wait for all workers to complete and aggregate results
            results = ray.get(gradient_futures)
            
            # Aggregate updated factors from all workers (average them)
            total_se = 0.0
            aggregated_user_factors = np.zeros_like(self.user_factors)
            aggregated_item_factors = np.zeros_like(self.item_factors)
            
            for updated_user_factors, updated_item_factors, se, n_samples in results:
                aggregated_user_factors += updated_user_factors
                aggregated_item_factors += updated_item_factors
                total_se += se
            
            # Average the updated factors from all workers
            self.user_factors = aggregated_user_factors / num_workers
            self.item_factors = aggregated_item_factors / num_workers
            
            rmse = math.sqrt(total_se / max(len(rr), 1))
            self.training_history.append(rmse)
            print("Epoch {}/{} - RMSE: {:.4f} (distributed across {} workers)".format(
                epoch + 1, self.n_epochs, rmse, num_workers))
            
            # Early stopping check
            if self.early_stopping:
                if rmse < best_rmse - self.min_delta:
                    best_rmse = rmse
                    patience_counter = 0
                else:
                    patience_counter += 1
                    if patience_counter >= self.patience:
                        print(f"Early stopping triggered at epoch {epoch + 1}. Best RMSE: {best_rmse:.4f}")
                        break

    def predict_one(self, user_id, item_id) -> float:
        if self.user_factors is None or self.item_factors is None:
            raise RuntimeError("Model not fitted")
        u = self.user_map.get(user_id)
        i = self.item_map.get(item_id)
        if u is None or i is None:
            return 0.0
        return float(np.dot(self.user_factors[u], self.item_factors[i]))

    def test(self, df: pd.DataFrame) -> Tuple[float, int]:
        # Returns (rmse, n)
        errs = []
        for _, row in df.iterrows():
            pred = self.predict_one(row['user_id'], row['product_id'])
            errs.append((row['rating'] - pred) ** 2)
        n = len(errs)
        rmse = math.sqrt(float(np.mean(errs))) if n else float('nan')
        return rmse, n
    
    def recommend_top_n(self, user_id, n=10, exclude_rated=None) -> List[Tuple[str, float]]:
        """
        Generate top-N recommendations for a user.
        
        Args:
            user_id: User to generate recommendations for
            n: Number of recommendations to return
            exclude_rated: Set of product IDs to exclude (already rated/purchased)
            
        Returns:
            List of (product_id, predicted_rating) tuples sorted by score
        """
        if self.user_factors is None or self.item_factors is None:
            raise RuntimeError("Model not fitted")
        
        u = self.user_map.get(user_id)
        if u is None:
            return []  # Cold start - user not in training data
        
        exclude_rated = exclude_rated or set()
        
        # Score all items
        scores = []
        for item_id in self.item_map.keys():
            if item_id not in exclude_rated:
                score = self.predict_one(user_id, item_id)
                scores.append((item_id, score))
        
        # Sort by score descending and return top-N
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:n]

def main():
    """
    Main Ray application to train a collaborative filtering recommendation model
    and save the artifact to S3.
    """
    try:
        # 1. Initialize Ray and Connect to the Cluster
        # =================================================================
        # Build address attempts
        if RAY_ADDRESS:
            attempts = [RAY_ADDRESS]
        else:
            attempts = ["auto", "ray-head:6379", "ray://ray-head:10001"]

        last_err = None
        connected = False
        for addr in attempts:
            try:
                print(f"Connecting to Ray with address='{addr}'...")
                ctx = ray.init(
                    address=addr, 
                    ignore_reinit_error=True,
                    # Limit object store memory to prevent OOM
                    _memory=2_000_000_000,  # 2GB for object store
                    _system_config={
                        "object_spilling_config": '{"type":"filesystem","params":{"directory_path":"/tmp/ray_spill"}}'
                    }
                )
                print(f"Ray initialized. Dashboard: {ctx.address_info.get('webui_url')}")
                last_err = None
                connected = True
                break
            except Exception as conn_err:
                print(f"Ray init failed for address '{addr}': {conn_err}")
                last_err = conn_err
        if not connected:
            warnings.warn(
                f"Ray connection failed; proceeding without Ray. Last error: {last_err}")
        else:
            print("Ray initialized successfully.")

        # 2. Load and Prepare Data for Training with Ray Data
        # Ray Data will distribute data loading across workers

        print("Loading training data with Ray Data (distributed across workers)...")

        # Build S3 path for Ray Data
        s3_path = f"s3://{S3_BUCKET}/{CLICKSTREAM_S3_KEY}"
        
        # Configure S3 filesystem for Ray Data (MinIO-compatible)
        # Ray Data will use these options to connect to MinIO
        import pyarrow.fs as pafs
        
        # Extract endpoint without protocol for pyarrow
        endpoint_no_protocol = MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
        
        # Create S3 filesystem for MinIO
        s3_fs = pafs.S3FileSystem(
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            endpoint_override=endpoint_no_protocol,
            scheme="http"  # MinIO typically uses http in k8s
        )
        
        print(f"Reading data from {s3_path} (distributed load across workers)...")
        
        # Configure Ray Data for memory-efficient processing
        ctx = ray.data.DataContext.get_current()
        ctx.execution_options.resource_limits.object_store_memory = 500_000_000  # 500MB per worker
        
        # Read JSON data with Ray Data - this distributes reading across workers
        clickstream_dataset = ray.data.read_json(
            s3_path,
            filesystem=s3_fs
        )
        
        print(f"Loaded {clickstream_dataset.count()} clickstream records using Ray Data.")
        
        # --- Feature Engineering: Create user-item "ratings" ---
        # Define event weights
        event_weights = {
            'view': 1.0,
            'add_to_cart': 3.0,
            'purchase': 5.0,
            'payment_failed': -2.0,
        }
        
        # Map ratings using Ray Data transformations (distributed across workers)
        # Use smaller batch sizes to reduce memory pressure
        def add_rating(batch):
            """Add rating column based on event_type"""
            import socket
            node_name = socket.gethostname()
            print(f"[Ray Data Worker on {node_name}] Processing {len(batch)} records...")
            batch['rating'] = batch['event_type'].map(event_weights)
            # Only keep columns we need
            return batch[['user_id', 'product_id', 'rating']]
        
        print("Transforming data (distributed processing across workers)...")
        clickstream_with_ratings = clickstream_dataset.map_batches(
            add_rating,
            batch_format="pandas",
            batch_size=5000  # Smaller batches to reduce memory usage
        )
        
        # Aggregate ratings by user-product pairs using map_batches with aggregation
        print("Aggregating ratings by user-product pairs (distributed)...")
        
        def aggregate_ratings_batch(batch):
            """Group by user_id and product_id, sum ratings within this batch"""
            return batch.groupby(['user_id', 'product_id'], as_index=False)['rating'].sum()
        
        # First: aggregate within each batch
        aggregated_batches = clickstream_with_ratings.map_batches(
            aggregate_ratings_batch,
            batch_format="pandas",
            batch_size=10000  # Process in manageable chunks
        )
        
        # Second: collect and do final aggregation (much smaller dataset now)
        # This is safe because we've already reduced the data size significantly
        print("Performing final aggregation...")
        ratings_list = []
        for batch in aggregated_batches.iter_batches(batch_size=50000, batch_format="pandas"):
            ratings_list.append(batch)
        
        # Combine and do final aggregation
        if ratings_list:
            combined_df = pd.concat(ratings_list, ignore_index=True)
            ratings_df = (
                combined_df.groupby(['user_id', 'product_id'], as_index=False)['rating']
                .sum()
            )
        else:
            ratings_df = pd.DataFrame(columns=['user_id', 'product_id', 'rating'])
        
        print(f"Created {len(ratings_df)} user-item ratings from clickstream data.")
        
        # Analyze rating distribution
        if not ratings_df.empty:
            print(f"Rating statistics (before normalization):")
            print(f"  Min: {ratings_df['rating'].min():.2f}")
            print(f"  Max: {ratings_df['rating'].max():.2f}")
            print(f"  Mean: {ratings_df['rating'].mean():.2f}")
            print(f"  Median: {ratings_df['rating'].median():.2f}")
            print(f"  Std: {ratings_df['rating'].std():.2f}")
        
        if ratings_df.empty:
            raise ValueError("Ratings data is empty after processing.")
        
        # Normalize ratings to 1-5 scale for better training
        # This prevents issues with very large aggregated ratings
        print("Normalizing ratings to 1-5 scale...")
        rating_min = ratings_df['rating'].min()
        rating_max = ratings_df['rating'].max()
        
        if rating_max > rating_min:
            # Min-max normalization to 1-5 range
            ratings_df['rating'] = 1 + 4 * (ratings_df['rating'] - rating_min) / (rating_max - rating_min)
        else:
            # All ratings are the same, just set to 3 (middle of range)
            ratings_df['rating'] = 3.0
        
        print(f"Normalized rating statistics:")
        print(f"  Min: {ratings_df['rating'].min():.2f}")
        print(f"  Max: {ratings_df['rating'].max():.2f}")
        print(f"  Mean: {ratings_df['rating'].mean():.2f}")

        # 3. Train the Recommendation Model (Pure NumPy FunkSVD)
        # =================================================================
        print("Splitting data into train/test...")
        # Simple split
        shuffled = ratings_df.sample(frac=1.0, random_state=42).reset_index(drop=True)
        split_idx = int(0.8 * len(shuffled))
        train_df = shuffled.iloc[:split_idx]
        test_df = shuffled.iloc[split_idx:]

        print("Training FunkSVD model with distributed Ray workers...")
        # Increased regularization to prevent overfitting, more epochs to converge
        # Early stopping with patience=3 to save compute when model plateaus
        model = FunkSVD(
            n_factors=20, 
            n_epochs=20, 
            lr=0.01, 
            reg=0.1, 
            random_state=42,
            early_stopping=True,
            patience=3,
            min_delta=0.0001
        )
        
        # Get number of available Ray workers - be conservative with parallelism to avoid OOM
        num_workers = 2  # Default to 2 workers as configured in ray.yaml
        if ray.is_initialized():
            resources = ray.cluster_resources()
            # Count available CPU resources to determine worker count
            available_cpus = resources.get('CPU', 0)
            # Reserve CPUs for the head node and limit parallelism to avoid memory issues
            # Each worker task will use 1 CPU
            num_workers = min(int(available_cpus) - 2, 4)  # Max 4 workers, reserve 2 CPUs
            num_workers = max(1, num_workers)  # At least 1 worker
            print(f"Ray cluster has {available_cpus} CPUs available. Using {num_workers} workers for training.")
        
        model.fit_distributed(train_df, num_workers=num_workers)

        # Evaluate the model
        rmse, n = model.test(test_df)

        print("\n--- Training Result ---")
        print(f"Training finished. Test RMSE: {rmse:.4f}")
        print(f"Trained on {len(train_df)} samples, tested on {len(test_df)} samples")
        print(f"Model covers {len(model.user_map)} users and {len(model.item_map)} items")
        print(f"Training epochs completed: {len(model.training_history)}")
        
        # Calculate additional metrics
        mae = 0.0
        for _, row in test_df.iterrows():
            pred = model.predict_one(row['user_id'], row['product_id'])
            mae += abs(row['rating'] - pred)
        mae /= len(test_df)
        print(f"Mean Absolute Error (MAE): {mae:.4f}")
        
        # Show sample recommendations for first few users
        print("\n--- Sample Recommendations ---")
        sample_users = list(model.user_map.keys())[:3]
        for user_id in sample_users:
            # Get items this user has rated
            user_rated = set(train_df[train_df['user_id'] == user_id]['product_id'].tolist())
            recommendations = model.recommend_top_n(user_id, n=5, exclude_rated=user_rated)
            print(f"User {user_id}: {[f'{prod}({score:.2f})' for prod, score in recommendations]}")
        print("-----------------------\n")

        trained_model = model

        # 4. Save the Trained Model to MinIO
        # =================================================================
        print(
            f"Saving trained model to S3 bucket '{S3_BUCKET}' at '{OUTPUT_MODEL_KEY}'..."
        )

        # Package model with metadata for production use
        model_package = {
            'model': trained_model,
            'metadata': {
                'rmse': rmse,
                'mae': mae,
                'n_users': len(trained_model.user_map),
                'n_items': len(trained_model.item_map),
                'n_factors': trained_model.n_factors,
                'training_samples': len(train_df),
                'test_samples': len(test_df),
                'epochs_completed': len(trained_model.training_history),
                'rating_min': float(rating_min),
                'rating_max': float(rating_max),
                'normalized': True
            }
        }
        
        model_bytes = pickle.dumps(model_package)

        # Create S3 client for model upload
        s3_client = boto3.client(
            's3',
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            config=_BotoCfg(signature_version='s3v4'),
        )
        
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=OUTPUT_MODEL_KEY,
            Body=model_bytes,
        )

        print("\n🎉 Training job completed successfully!")

    except Exception as e:
        print(f"An error occurred during the Ray job: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ray.is_initialized():
            print("Shutting down Ray connection.")
            ray.shutdown()

if __name__ == "__main__":
    main()
