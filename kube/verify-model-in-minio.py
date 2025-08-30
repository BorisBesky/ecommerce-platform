#!/usr/bin/env python3

"""
Verify and download the trained recommendation model from MinIO.
This script checks the model exists and optionally downloads it for testing.
"""

import os
import pickle
import boto3
from botocore.config import Config
from pathlib import Path

# MinIO Configuration
MINIO_ENDPOINT = "http://localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
S3_BUCKET = "warehouse"
MODEL_KEY = "models/recommendation_model.pkl"

def setup_minio_client():
    """Create and configure MinIO client."""
    return boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )

def verify_model_in_minio(s3_client):
    """Verify the model exists in MinIO and get metadata."""
    try:
        response = s3_client.head_object(Bucket=S3_BUCKET, Key=MODEL_KEY)
        size_mb = response['ContentLength'] / (1024 * 1024)
        last_modified = response['LastModified']
        
        print(f"✅ Model found in MinIO!")
        print(f"   📍 Location: s3://{S3_BUCKET}/{MODEL_KEY}")
        print(f"   📊 Size: {size_mb:.2f} MB")
        print(f"   📅 Last Modified: {last_modified}")
        
        return True
    except Exception as e:
        print(f"❌ Model not found in MinIO: {e}")
        return False

def download_and_test_model(s3_client):
    """Download the model and test its functionality."""
    try:
        print(f"\n📥 Downloading model from MinIO...")
        
        # Download model
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=MODEL_KEY)
        model_bytes = response['Body'].read()
        
        # Deserialize model
        model = pickle.loads(model_bytes)
        
        print(f"✅ Model downloaded and loaded successfully!")
        print(f"   🧠 Model type: {type(model).__name__}")
        print(f"   👥 Users in model: {len(model.user_map):,}")
        print(f"   🛍️  Items in model: {len(model.item_map):,}")
        print(f"   🔢 Latent factors: {model.n_factors}")
        print(f"   📈 Training epochs: {model.n_epochs}")
        
        # Test a prediction
        if model.user_map and model.item_map:
            sample_user = list(model.user_map.keys())[0]
            sample_item = list(model.item_map.keys())[0]
            prediction = model.predict_one(sample_user, sample_item)
            print(f"   🎯 Sample prediction: user='{sample_user[:20]}...', item='{sample_item[:20]}...', rating={prediction:.4f}")
        
        # Optionally save locally
        local_dir = Path(__file__).parent.parent / "models"
        local_dir.mkdir(exist_ok=True)
        local_path = local_dir / "recommendation_model.pkl"
        
        with open(local_path, 'wb') as f:
            f.write(model_bytes)
        print(f"   💾 Model saved locally: {local_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to download/test model: {e}")
        return False

def list_all_models(s3_client):
    """List all models in the MinIO bucket."""
    try:
        print(f"\n📋 All models in MinIO bucket '{S3_BUCKET}':")
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix="models/")
        
        if 'Contents' in response:
            for obj in response['Contents']:
                size_mb = obj['Size'] / (1024 * 1024)
                print(f"   📄 {obj['Key']} ({size_mb:.2f} MB) - {obj['LastModified']}")
        else:
            print("   No models found in bucket")
            
    except Exception as e:
        print(f"⚠️  Could not list models: {e}")

def main():
    """Main function to verify and download the trained model."""
    print("🔍 Verifying Ray Recommendation Model in MinIO")
    print("=" * 50)
    
    # Setup MinIO client
    try:
        s3_client = setup_minio_client()
        print("✅ MinIO client configured")
    except Exception as e:
        print(f"❌ Failed to configure MinIO client: {e}")
        return False
    
    # Verify specific model
    model_exists = verify_model_in_minio(s3_client)
    
    if model_exists:
        # Download and test the model
        download_success = download_and_test_model(s3_client)
        
        if download_success:
            print(f"\n🎉 Model verification and download completed successfully!")
        else:
            print(f"\n⚠️  Model exists but download/testing failed")
    else:
        print(f"\n❌ Model not found. Please run the training job first.")
    
    # List all models
    list_all_models(s3_client)
    
    print(f"\n🌐 MinIO Console: http://localhost:9001 (minioadmin/minioadmin)")
    print(f"📡 MinIO API: {MINIO_ENDPOINT}")
    
    return model_exists

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1)
