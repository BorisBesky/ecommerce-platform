#!/usr/bin/env python3

"""
Upload ecommerce dataset artifacts (users, products, clickstream) to a MinIO / S3-compatible bucket.

Features:
    * Upload users.csv & products.csv to s3://<bucket>/data/
    * Upload clickstream-*.json files under s3://<bucket>/data/clickstream/individual/
    * Upload stable alias clickstream.json to s3://<bucket>/data/clickstream/clickstream.json
    * Configurable via CLI arguments & environment variables.

CLI Example:
    python tools/upload-data-to-minio.py \
        --endpoint http://localhost:9000 \
        --access-key minioadmin --secret-key minioadmin \
        --bucket warehouse --data-dir data --include users products clickstream
"""

import os
import boto3
import glob
import argparse
from botocore.config import Config
from pathlib import Path
from typing import List

def parse_args():
    parser = argparse.ArgumentParser(description="Upload ecommerce data assets to MinIO/S3 compatible storage")
    parser.add_argument("--endpoint", default=os.environ.get("MINIO_ENDPOINT", "http://localhost:9000"), help="MinIO/S3 endpoint URL")
    parser.add_argument("--access-key", default=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"), help="Access key")
    parser.add_argument("--secret-key", default=os.environ.get("MINIO_SECRET_KEY", "minioadmin"), help="Secret key")
    parser.add_argument("--bucket", default=os.environ.get("DATA_BUCKET", "warehouse"), help="Target bucket")
    parser.add_argument("--data-dir", default="data", help="Local data directory containing generated files")
    parser.add_argument("--include", nargs="+", choices=["users", "products", "clickstream"], default=["users", "products", "clickstream"], help="Which artifact groups to upload")
    parser.add_argument("--skip-individual", action="store_true", help="Skip uploading individual clickstream-*.json files (only alias)")
    parser.add_argument("--prefix", default="data", help="Root prefix inside bucket (default: data)")
    return parser.parse_args()

class UploaderConfig:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str, data_dir: Path, include: List[str], prefix: str, skip_individual: bool):
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.data_dir = data_dir
        self.include = include
        self.prefix = prefix.rstrip('/')
        self.skip_individual = skip_individual

def setup_minio_client(cfg: UploaderConfig):
    """Create and configure MinIO client."""
    return boto3.client(
        's3',
        endpoint_url=cfg.endpoint,
        aws_access_key_id=cfg.access_key,
        aws_secret_access_key=cfg.secret_key,
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

def upload_artifacts(cfg: UploaderConfig) -> bool:
    print("🚀 Uploading data artifacts to MinIO/S3...")
    data_dir = cfg.data_dir
    print(f"📂 Local data directory: {data_dir}")

    if not data_dir.exists():
        print(f"❌ Data directory '{data_dir}' does not exist")
        return False

    try:
        s3_client = setup_minio_client(cfg)
        print("✅ MinIO/S3 client configured")
    except Exception as e:
        print(f"❌ Failed to configure client: {e}")
        return False

    try:
        create_bucket_if_not_exists(s3_client, cfg.bucket)
    except Exception as e:
        print(f"❌ Bucket setup failed: {e}")
        return False

    success_count = 0

    # Users / Products
    if "users" in cfg.include:
        users_path = data_dir / "users.csv"
        if users_path.exists():
            key = f"{cfg.prefix}/users.csv"
            if upload_file_to_minio(s3_client, str(users_path), cfg.bucket, key):
                success_count += 1
        else:
            print("⚠️ users.csv not found; skipping")

    if "products" in cfg.include:
        products_path = data_dir / "products.csv"
        if products_path.exists():
            key = f"{cfg.prefix}/products.csv"
            if upload_file_to_minio(s3_client, str(products_path), cfg.bucket, key):
                success_count += 1
        else:
            print("⚠️ products.csv not found; skipping")

    # Clickstream
    if "clickstream" in cfg.include:
        individual_dir_key_root = f"{cfg.prefix}/clickstream/individual".rstrip('/') + '/'
        files = sorted(glob.glob(str(data_dir / "clickstream-*.json")))
        merged_file = data_dir / "clickstream.json"

        if not files and not merged_file.exists():
            print("⚠️ No clickstream files found; skipping clickstream uploads")
        else:
            if not cfg.skip_individual:
                print(f"📋 Found {len(files)} individual clickstream files")
                for fp in files:
                    filename = os.path.basename(fp)
                    key = f"{individual_dir_key_root}{filename}"
                    if upload_file_to_minio(s3_client, fp, cfg.bucket, key):
                        success_count += 1
            if merged_file.exists():
                alias_key = f"{cfg.prefix}/clickstream/clickstream.json"
                if upload_file_to_minio(s3_client, str(merged_file), cfg.bucket, alias_key):
                    success_count += 1
                    print(f"✅ Stable alias uploaded: s3://{cfg.bucket}/{alias_key}")
            else:
                print("⚠️ Stable clickstream.json not found")

    # Summary
    print("\n📊 Upload Summary")
    print(f"   Total successful uploads: {success_count}")
    try:
        prefix_list = f"{cfg.prefix}/clickstream/"
        response = s3_client.list_objects_v2(Bucket=cfg.bucket, Prefix=prefix_list)
        if 'Contents' in response:
            print(f"\n📋 Objects under {prefix_list}:")
            for obj in response['Contents'][:25]:  # limit listing
                print(f"   • {obj['Key']} ({obj['Size']} bytes)")
        else:
            print(f"No objects listed under {prefix_list}")
    except Exception as e:
        print(f"⚠️ Could not list objects: {e}")

    print("\n✅ Data upload operation finished")
    print(f"Endpoint: {cfg.endpoint}")
    print(f"Bucket:   {cfg.bucket}")
    return success_count > 0

def main():
    args = parse_args()
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = project_root / data_dir

    cfg = UploaderConfig(
        endpoint=args.endpoint,
        access_key=args.access_key,
        secret_key=args.secret_key,
        bucket=args.bucket,
        data_dir=data_dir,
        include=args.include,
        prefix=args.prefix,
        skip_individual=args.skip_individual,
    )
    return upload_artifacts(cfg)

if __name__ == "__main__":
    ok = main()
    if not ok:
        exit(1)
