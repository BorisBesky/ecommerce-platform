import os
import glob
import math
import pickle
from typing import Dict, Tuple, Optional
import warnings

import numpy as np
import pandas as pd
import ray
import boto3
from botocore.config import Config
import io

# --- Configuration ---
# Ray connection address strategy:
# - If RAY_ADDRESS env var is set, use that (e.g., "ray://ray-head:10001" or "ray-head:6379" or "auto").
# - Otherwise, try a sensible sequence for in-cluster runs: auto -> tcp -> client.
RAY_ADDRESS = os.environ.get("RAY_ADDRESS")

# MinIO Configuration - use environment variables if available
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://host.docker.internal:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
S3_BUCKET = "warehouse"
DATA_KEY = "data/clickstream/clickstream.json"
OUTPUT_MODEL_KEY = "models/recommendation_model.pkl"

# ------------------------
# Simple FunkSVD (SGD) Recommender (pure NumPy)
# ------------------------
class FunkSVD:
    def __init__(self, n_factors=20, n_epochs=10, lr=0.005, reg=0.05, random_state=42):
        self.n_factors = n_factors
        self.n_epochs = n_epochs
        self.lr = lr
        self.reg = reg
        self.random_state = random_state
        self.user_factors = None  # type: Optional[np.ndarray]
        self.item_factors = None  # type: Optional[np.ndarray]
        self.user_map = {}  # type: Dict
        self.item_map = {}  # type: Dict
        self.user_inv = {}  # type: Dict
        self.item_inv = {}  # type: Dict

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
                if err > 5.0:
                    err = 5.0
                elif err < -5.0:
                    err = -5.0
                se += err * err
                # SGD updates
                self.user_factors[u] += self.lr * (err * qi - self.reg * pu)
                self.item_factors[i] += self.lr * (err * pu - self.reg * qi)
                # Clamp factor values to avoid explosion
                self.user_factors[u] = np.clip(self.user_factors[u], -5.0, 5.0)
                self.item_factors[i] = np.clip(self.item_factors[i], -5.0, 5.0)
            rmse = math.sqrt(se / max(len(rr), 1))
            print("Epoch {}/{} - RMSE: {:.4f}".format(epoch + 1, self.n_epochs, rmse))

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

def setup_s3_client():
    """Create and configure S3/MinIO client."""
    return boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )

def load_data_from_minio(s3_client):
    """Load clickstream data from MinIO."""
    try:
        print(f"📥 Loading data from MinIO: s3://{S3_BUCKET}/{DATA_KEY}")
        
        # Get object from MinIO
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=DATA_KEY)
        content = response['Body'].read().decode('utf-8')
        
        # Parse JSON lines
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        clickstream_df = pd.read_json(io.StringIO('\n'.join(lines)), lines=True)
        
        print(f"✅ Loaded {len(clickstream_df)} records from MinIO")
        return clickstream_df
        
    except Exception as e:
        print(f"❌ Failed to load data from MinIO: {e}")
        raise

def save_model_to_minio(s3_client, model):
    """Save trained model to MinIO."""
    try:
        print(f"💾 Saving model to MinIO: s3://{S3_BUCKET}/{OUTPUT_MODEL_KEY}")
        
        # Serialize model
        model_bytes = pickle.dumps(model)
        
        # Upload to MinIO
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=OUTPUT_MODEL_KEY,
            Body=model_bytes,
            ContentType='application/octet-stream'
        )
        
        print(f"✅ Model saved successfully to MinIO")
        
        # Verify the upload
        response = s3_client.head_object(Bucket=S3_BUCKET, Key=OUTPUT_MODEL_KEY)
        size_mb = response['ContentLength'] / (1024 * 1024)
        print(f"📊 Model size: {size_mb:.2f} MB")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to save model to MinIO: {e}")
        return False

def generate_sample_data(n_users=1000, n_items=500, n_interactions=10000):
    """Generate sample clickstream data for training (fallback)."""
    print(f"🎲 Generating sample data: {n_users} users, {n_items} items, {n_interactions} interactions...")
    
    rng = np.random.default_rng(42)
    
    # Generate user and item IDs
    user_ids = [f"user_{i:06d}" for i in range(n_users)]
    product_ids = [f"product_{i:06d}" for i in range(n_items)]
    
    event_types = ['view', 'add_to_cart', 'purchase', 'payment_failed']
    event_weights = [0.7, 0.2, 0.08, 0.02]  # Probabilities for each event type
    
    # Generate interactions
    data = []
    for _ in range(n_interactions):
        user_id = rng.choice(user_ids)
        product_id = rng.choice(product_ids)
        event_type = rng.choice(event_types, p=event_weights)
        
        data.append({
            'timestamp': '2025-08-19T12:00:00Z',  # Fixed timestamp for simplicity
            'user_id': user_id,
            'product_id': product_id,
            'event_type': event_type
        })
    
    return pd.DataFrame(data)

def main():
    """
    Main Ray application to train a collaborative filtering recommendation model
    and save the artifact to MinIO.
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
                print(f"🔗 Connecting to Ray with address='{addr}'...")
                ctx = ray.init(address=addr, ignore_reinit_error=True)
                print(f"✅ Ray initialized. Dashboard: {ctx.address_info.get('webui_url')}")
                last_err = None
                connected = True
                break
            except Exception as conn_err:
                print(f"⚠️  Ray init failed for address '{addr}': {conn_err}")
                last_err = conn_err
        if not connected:
            warnings.warn(
                f"Ray connection failed; proceeding without Ray. Last error: {last_err}")
        else:
            print("✅ Ray initialized successfully.")

        # 2. Setup MinIO Client
        # =================================================================
        print(f"🔧 Setting up MinIO client (endpoint: {MINIO_ENDPOINT})")
        try:
            s3_client = setup_s3_client()
            # Test connection
            s3_client.head_bucket(Bucket=S3_BUCKET)
            print("✅ MinIO connection successful")
        except Exception as e:
            print(f"❌ MinIO connection failed: {e}")
            print("🎲 Will use sample data and skip model saving")
            s3_client = None

        # 3. Load and Prepare Data for Training
        # =================================================================
        print("📊 Loading training data...")
        
        clickstream_df = None
        
        # Try to load real data from MinIO
        if s3_client:
            try:
                clickstream_df = load_data_from_minio(s3_client)
            except Exception as e:
                print(f"⚠️  Failed to load from MinIO: {e}")
        
        # Fallback to sample data if MinIO loading failed
        if clickstream_df is None:
            print("🎲 Using sample data for demonstration...")
            clickstream_df = generate_sample_data()

        print(f"📈 Loaded {len(clickstream_df)} clickstream records.")

        # --- Feature Engineering: Create user-item "ratings" ---
        event_weights = {
            'view': 1.0,
            'add_to_cart': 3.0,
            'purchase': 5.0,
            'payment_failed': -2.0,
        }
        clickstream_df['rating'] = clickstream_df['event_type'].map(event_weights)

        ratings_df = (
            clickstream_df.groupby(['user_id', 'product_id'])['rating']
            .sum()
            .reset_index()
        )
        print(f"🔢 Created {len(ratings_df)} user-item ratings from clickstream data.")

        # 4. Train the Recommendation Model (Pure NumPy FunkSVD)
        # =================================================================
        print("🚀 Starting model training...")
        # Simple split
        shuffled = ratings_df.sample(frac=1.0, random_state=42).reset_index(drop=True)
        split_idx = int(0.8 * len(shuffled))
        train_df = shuffled.iloc[:split_idx]
        test_df = shuffled.iloc[split_idx:]

        print(f"📊 Training set: {len(train_df)} samples")
        print(f"📊 Test set: {len(test_df)} samples")

        print("🧠 Training FunkSVD model...")
        model = FunkSVD(n_factors=20, n_epochs=10, lr=0.01, reg=0.02, random_state=42)
        model.fit(train_df)

        # Evaluate the model
        rmse, n = model.test(test_df)

        print("\n" + "="*50)
        print("🎯 TRAINING RESULTS")
        print("="*50)
        print(f"✅ Training completed successfully!")
        print(f"📊 Final model accuracy (RMSE): {rmse:.4f}")
        print(f"📈 Training samples: {len(train_df):,}")
        print(f"📉 Test samples: {len(test_df):,}")
        print(f"👥 Users covered: {len(model.user_map):,}")
        print(f"🛍️  Items covered: {len(model.item_map):,}")
        print("="*50 + "\n")

        # 5. Save the Trained Model to MinIO
        # =================================================================
        if s3_client:
            success = save_model_to_minio(s3_client, model)
            if success:
                print("🎉 Model successfully saved to MinIO!")
            else:
                print("⚠️  Model training successful but saving failed")
        else:
            print("⚠️  Skipping model save due to MinIO connection issues")

        print("\n🎉 Training job completed successfully!")

    except Exception as e:
        print(f"❌ An error occurred during the Ray job: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ray.is_initialized():
            print("🔚 Shutting down Ray connection.")
            ray.shutdown()

if __name__ == "__main__":
    main()
