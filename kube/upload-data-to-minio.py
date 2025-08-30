#!/usr/bin/env python3

"""
Upload clickstream data to MinIO bucket for Ray training job.
This script uploads individual clickstream files and the merged file to MinIO.
"""

import os
import boto3
import glob
from botocore.config import Config
from pathlib import Path

# MinIO Configuration
MINIO_ENDPOINT = "http://localhost:9000"  # Local MinIO endpoint
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
S3_BUCKET = "warehouse"
DATA_PREFIX = "data/clickstream/"

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

def create_bucket_if_not_exists(s3_client, bucket_name):
    """Create bucket if it doesn't exist."""
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"✅ Bucket '{bucket_name}' already exists")
    except Exception:
        try:
            s3_client.create_bucket(Bucket=bucket_name)
            print(f"✅ Created bucket '{bucket_name}'")
        except Exception as e:
            print(f"❌ Failed to create bucket '{bucket_name}': {e}")
            raise

def upload_file_to_minio(s3_client, local_path, bucket, key):
    """Upload a file to MinIO."""
    try:
        file_size = os.path.getsize(local_path)
        print(f"📤 Uploading {os.path.basename(local_path)} ({file_size:,} bytes) to s3://{bucket}/{key}")
        
        s3_client.upload_file(local_path, bucket, key)
        print(f"✅ Upload successful: s3://{bucket}/{key}")
        return True
    except Exception as e:
        print(f"❌ Upload failed for {local_path}: {e}")
        return False

def main():
    """Main function to upload clickstream data to MinIO."""
    print("🚀 Uploading clickstream data to MinIO...")
    
    # Get data directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    data_dir = project_root / "data"
    
    print(f"📂 Data directory: {data_dir}")
    
    # Setup MinIO client
    try:
        s3_client = setup_minio_client()
        print("✅ MinIO client configured")
    except Exception as e:
        print(f"❌ Failed to configure MinIO client: {e}")
        return False
    
    # Create bucket
    try:
        create_bucket_if_not_exists(s3_client, S3_BUCKET)
    except Exception as e:
        print(f"❌ Bucket setup failed: {e}")
        return False
    
    # Find clickstream files
    clickstream_files = sorted(glob.glob(str(data_dir / "clickstream-*.json")))
    merged_file = data_dir / "clickstream.json"
    
    if not clickstream_files:
        print("❌ No clickstream files found!")
        return False
    
    print(f"📋 Found {len(clickstream_files)} individual clickstream files")
    
    # Upload individual files
    success_count = 0
    for file_path in clickstream_files:
        filename = os.path.basename(file_path)
        s3_key = f"{DATA_PREFIX}individual/{filename}"
        if upload_file_to_minio(s3_client, file_path, S3_BUCKET, s3_key):
            success_count += 1
    
    # Upload merged file if it exists
    if merged_file.exists():
        s3_key = f"{DATA_PREFIX}clickstream.json"
        if upload_file_to_minio(s3_client, str(merged_file), S3_BUCKET, s3_key):
            success_count += 1
            print(f"✅ Merged file uploaded: s3://{S3_BUCKET}/{s3_key}")
    else:
        print("⚠️  Merged clickstream.json file not found. Run prepare-data.py first if needed.")
    
    # List uploaded files
    print(f"\n📊 Upload Summary:")
    print(f"   Successfully uploaded: {success_count} files")
    
    try:
        print(f"\n📋 Files in MinIO bucket '{S3_BUCKET}':")
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=DATA_PREFIX)
        if 'Contents' in response:
            for obj in response['Contents']:
                size_mb = obj['Size'] / (1024 * 1024)
                print(f"   📄 {obj['Key']} ({size_mb:.2f} MB)")
        else:
            print("   No files found in bucket")
    except Exception as e:
        print(f"⚠️  Could not list bucket contents: {e}")
    
    print(f"\n✅ Data upload completed!")
    print(f"🌐 MinIO Console: http://localhost:9001 (admin/minioadmin)")
    print(f"📡 MinIO API: {MINIO_ENDPOINT}")
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1)
