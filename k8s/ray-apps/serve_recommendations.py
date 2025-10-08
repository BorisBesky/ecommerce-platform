import os
import pickle
import math
from typing import List, Dict, Optional, Tuple
import numpy as np
import boto3
from botocore.config import Config
from ray import serve
from starlette.requests import Request

# --- Configuration ---
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
S3_BUCKET = os.environ.get("MODEL_S3_BUCKET", "warehouse")
MODEL_KEY = os.environ.get("MODEL_KEY", "models/recommendation_model.pkl")


# ------------------------
# FunkSVD Model Class (needed for unpickling)
# ------------------------
class FunkSVD:
    """
    Simple FunkSVD (SGD) Recommender (pure NumPy).
    This class definition is needed to unpickle the trained model.
    """
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
        self.user_factors = None
        self.item_factors = None
        self.user_map = {}
        self.item_map = {}
        self.user_inv = {}
        self.item_inv = {}
        self.training_history = []

    def predict_one(self, user_id, item_id) -> float:
        if self.user_factors is None or self.item_factors is None:
            raise RuntimeError("Model not fitted")
        u = self.user_map.get(user_id)
        i = self.item_map.get(item_id)
        if u is None or i is None:
            return 0.0
        return float(np.dot(self.user_factors[u], self.item_factors[i]))

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


@serve.deployment(
    ray_actor_options={"num_cpus": 0.5},
    autoscaling_config={
        "min_replicas": 1,
        "max_replicas": 3,
        "target_num_ongoing_requests_per_replica": 5,
    },
)
class RecommendationService:
    """Ray Serve deployment that loads the trained model and serves recommendations."""
    
    def __init__(self):
        print(f"Loading recommendation model from s3://{S3_BUCKET}/{MODEL_KEY}...")
        self.model_package = self._load_model()
        self.model = self.model_package['model']
        self.metadata = self.model_package.get('metadata', {})
        print(f"Model loaded successfully!")
        print(f"  Users: {self.metadata.get('n_users', 'unknown')}")
        print(f"  Items: {self.metadata.get('n_items', 'unknown')}")
        print(f"  Test RMSE: {self.metadata.get('rmse', 'unknown')}")
    
    def _load_model(self):
        """Load the trained model from MinIO."""
        import sys
        import io
        
        s3_client = boto3.client(
            's3',
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            config=Config(signature_version='s3v4'),
        )
        
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=MODEL_KEY)
        model_bytes = response['Body'].read()
        
        # Custom unpickler to handle FunkSVD class
        class CustomUnpickler(pickle.Unpickler):
            def find_class(self, module, name):
                # If looking for FunkSVD in __main__, redirect to this module
                if name == 'FunkSVD':
                    return FunkSVD
                return super().find_class(module, name)
        
        model_package = CustomUnpickler(io.BytesIO(model_bytes)).load()
        return model_package
    
    async def __call__(self, request: Request) -> Dict:
        """
        Handle HTTP requests for recommendations.
        
        Expected JSON body:
        {
            "user_id": "user123",
            "n": 5,
            "exclude_products": ["prod1", "prod2"]  # optional
        }
        
        Returns:
        {
            "user_id": "user123",
            "recommendations": [
                {"product_id": "prod10", "score": 4.5},
                {"product_id": "prod20", "score": 4.2},
                ...
            ],
            "metadata": {
                "model_rmse": 0.48,
                "n_users": 200,
                "n_items": 100
            }
        }
        """
        try:
            data = await request.json()
            user_id = data.get("user_id")
            n = data.get("n", 5)
            exclude_products = set(data.get("exclude_products", []))
            
            if not user_id:
                return {"error": "user_id is required"}
            
            # Get recommendations using the model
            recommendations = self.model.recommend_top_n(
                user_id=user_id,
                n=n,
                exclude_rated=exclude_products
            )
            
            # Format response
            return {
                "user_id": user_id,
                "recommendations": [
                    {"product_id": prod_id, "score": float(score)}
                    for prod_id, score in recommendations
                ],
                "metadata": {
                    "model_rmse": self.metadata.get('rmse'),
                    "model_mae": self.metadata.get('mae'),
                    "n_users": self.metadata.get('n_users'),
                    "n_items": self.metadata.get('n_items')
                }
            }
        except Exception as e:
            return {"error": str(e)}


# Build and deploy the application
app = RecommendationService.bind()