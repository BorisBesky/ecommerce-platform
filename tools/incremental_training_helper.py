#!/usr/bin/env python3
"""
Helper script for incremental model training workflows.

This script provides utilities to:
- Upload new clickstream data to MinIO
- Trigger incremental training
- Monitor training status
- Archive and manage data
"""

import os
import sys
import json
import argparse
import pickle
from datetime import datetime
from typing import List, Dict
import boto3
from botocore.config import Config


# Configuration
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
S3_BUCKET = os.environ.get("S3_BUCKET", "warehouse")
NEW_DATA_KEY = "data/clickstream_new.json"
MODEL_KEY = "models/prio_aware_recommendation_model.pkl"


def get_s3_client():
    """Create and return boto3 S3 client."""
    return boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4')
    )


def upload_new_clickstream(file_path: str):
    """
    Upload new clickstream data to MinIO for incremental training.
    
    Args:
        file_path: Path to JSON file containing new clickstream events
    """
    s3_client = get_s3_client()
    
    print(f"📤 Uploading {file_path} to s3://{S3_BUCKET}/{NEW_DATA_KEY}...")
    
    with open(file_path, 'r') as f:
        data = f.read()
    
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=NEW_DATA_KEY,
        Body=data.encode()
    )
    
    print(f"✓ Upload complete!")
    
    # Count records
    lines = data.strip().split('\n')
    print(f"  Records uploaded: {len(lines)}")


def check_new_data():
    """Check if new data is available for incremental training."""
    s3_client = get_s3_client()
    
    try:
        response = s3_client.head_object(Bucket=S3_BUCKET, Key=NEW_DATA_KEY)
        size_kb = response['ContentLength'] / 1024
        last_modified = response['LastModified']
        
        print(f"✓ New data available:")
        print(f"  Location: s3://{S3_BUCKET}/{NEW_DATA_KEY}")
        print(f"  Size: {size_kb:.2f} KB")
        print(f"  Last Modified: {last_modified}")
        
        # Try to count records
        try:
            obj = s3_client.get_object(Bucket=S3_BUCKET, Key=NEW_DATA_KEY)
            data = obj['Body'].read().decode()
            lines = data.strip().split('\n')
            print(f"  Estimated Records: {len(lines)}")
        except Exception:
            pass
        
        return True
    except s3_client.exceptions.ClientError:
        print(f"✗ No new data found at s3://{S3_BUCKET}/{NEW_DATA_KEY}")
        return False


def get_model_info():
    """Get information about the current model."""
    s3_client = get_s3_client()
    
    try:
        print(f"📊 Loading model info from s3://{S3_BUCKET}/{MODEL_KEY}...")
        
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=MODEL_KEY)
        model_bytes = response['Body'].read()
        model_package = pickle.loads(model_bytes)
        
        metadata = model_package.get('metadata', {})
        
        print(f"\n=== Model Information ===")
        print(f"  Model Type: {metadata.get('model_type', 'unknown')}")
        print(f"  Training Mode: {metadata.get('training_mode', 'unknown')}")
        print(f"  Last Updated: {metadata.get('last_updated', 'unknown')}")
        print(f"  Users: {metadata.get('n_users', 'unknown'):,}")
        print(f"  Items: {metadata.get('n_items', 'unknown'):,}")
        print(f"  Embedding Dimensions: {metadata.get('n_factors', 'unknown')}")
        print(f"  Sequence Length: {metadata.get('sequence_length', 'unknown')}")
        print(f"  Epochs Completed: {metadata.get('epochs_completed', 'unknown')}")
        print(f"  Final Loss: {metadata.get('final_loss', 'unknown')}")
        print(f"  Total Training Samples: {metadata.get('total_training_samples', 'unknown'):,}")
        print(f"  Model Size: {len(model_bytes) / 1024:.2f} KB")
        
        return metadata
    except s3_client.exceptions.NoSuchKey:
        print(f"✗ No model found at s3://{S3_BUCKET}/{MODEL_KEY}")
        return None
    except Exception as e:
        print(f"⚠ Error loading model: {e}")
        return None


def list_archives():
    """List archived clickstream data files."""
    s3_client = get_s3_client()
    
    print(f"📂 Archived Clickstream Data:")
    
    try:
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix='data/clickstream_archive_'
        )
        
        if 'Contents' not in response:
            print("  No archives found.")
            return
        
        archives = sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True)
        
        for obj in archives:
            key = obj['Key']
            size_kb = obj['Size'] / 1024
            modified = obj['LastModified']
            print(f"  - {key} ({size_kb:.2f} KB, {modified})")
        
        print(f"\n  Total archives: {len(archives)}")
    except Exception as e:
        print(f"⚠ Error listing archives: {e}")


def generate_sample_data(output_file: str, num_events: int = 100):
    """
    Generate sample clickstream data for testing.
    
    Args:
        output_file: Path to output JSON file
        num_events: Number of events to generate
    """
    import random
    
    print(f"🎲 Generating {num_events} sample clickstream events...")
    
    users = [f"user_{i:03d}" for i in range(1, 21)]
    products = [f"prod_{i:03d}" for i in range(1, 51)]
    
    events = []
    base_timestamp = datetime.now()
    
    for i in range(num_events):
        event = {
            "user_id": random.choice(users),
            "product_id": random.choice(products),
            "timestamp": (base_timestamp.timestamp() + i * 60)  # 1 minute apart
        }
        events.append(event)
    
    # Write as JSON lines
    with open(output_file, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')
    
    print(f"✓ Sample data written to {output_file}")
    print(f"  Users: {len(set(e['user_id'] for e in events))}")
    print(f"  Products: {len(set(e['product_id'] for e in events))}")


def main():
    parser = argparse.ArgumentParser(
        description='Helper script for incremental model training',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check for new data
  python incremental_training_helper.py check
  
  # Upload new clickstream data
  python incremental_training_helper.py upload new_events.json
  
  # Get current model information
  python incremental_training_helper.py info
  
  # List archived data
  python incremental_training_helper.py archives
  
  # Generate sample data for testing
  python incremental_training_helper.py generate sample_data.json --events 500
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Upload command
    upload_parser = subparsers.add_parser('upload', help='Upload new clickstream data')
    upload_parser.add_argument('file', help='Path to JSON file with new clickstream events')
    
    # Check command
    subparsers.add_parser('check', help='Check if new data is available')
    
    # Info command
    subparsers.add_parser('info', help='Get current model information')
    
    # Archives command
    subparsers.add_parser('archives', help='List archived clickstream data')
    
    # Generate command
    generate_parser = subparsers.add_parser('generate', help='Generate sample clickstream data')
    generate_parser.add_argument('output', help='Output file path')
    generate_parser.add_argument('--events', type=int, default=100, help='Number of events to generate')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'upload':
            upload_new_clickstream(args.file)
        elif args.command == 'check':
            check_new_data()
        elif args.command == 'info':
            get_model_info()
        elif args.command == 'archives':
            list_archives()
        elif args.command == 'generate':
            generate_sample_data(args.output, args.events)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
