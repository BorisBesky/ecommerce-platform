import argparse
import csv
import json
import os
import random
import uuid
from datetime import datetime, timedelta
import shutil
import numpy as np
import boto3
from botocore.config import Config
from pathlib import Path

# --- Constants ---
FIRST_NAMES = ['John', 'Jane', 'Peter', 'Mary', 'Chris', 'Pat', 'Alex', 'Sam', 'Taylor', 'Jordan']
LAST_NAMES = ['Smith', 'Jones', 'Williams', 'Brown', 'Davis', 'Miller', 'Wilson', 'Moore', 'Taylor', 'Anderson']
PRODUCT_NOUNS = ['Keyboard', 'Mouse', 'Monitor', 'Chair', 'Desk', 'Webcam', 'Headset', 'Laptop', 'Dock', 'Cable']
PRODUCT_ADJECTIVES = ['Ergonomic', 'Mechanical', 'Gaming', 'Wireless', '4K', 'Curved', 'Standing', 'Adjustable', 'HD']
CATEGORIES = ['Electronics', 'Office', 'Peripherals', 'Furniture', 'Accessories']
EVENT_TYPES = ['view', 'view', 'view', 'view', 'add_to_cart', 'add_to_cart', 'purchase', 'payment_failed']

class DataGenerator:
    def __init__(self, num_users, num_products, num_events, output_dir, seed=None):
        self.num_users = num_users
        self.num_products = num_products
        self.num_events = num_events
        self.output_dir = output_dir
        self.user_ids = []
        self.product_ids = []
        self.user_features = {}
        self.product_features = {}

        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            print(f"Created directory: '{self.output_dir}'")

    def generate_users(self):
        """Generates a CSV file with mock user data with 20-dimensional feature vectors."""
        file_path = os.path.join(self.output_dir, 'users.csv')
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['user_id', 'name', 'signup_date', 'features'])
            for _ in range(self.num_users):
                user_id = str(uuid.uuid4())
                self.user_ids.append(user_id)
                name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
                signup_date = (datetime.now() - timedelta(days=random.randint(1, 365))).strftime('%Y-%m-%d')
                features = np.random.randn(20)
                features = features / np.linalg.norm(features)
                self.user_features[user_id] = features
                features_str = json.dumps(features.tolist())
                writer.writerow([user_id, name, signup_date, features_str])
        print(f"Successfully generated {self.num_users} users in '{file_path}'")
        return file_path

    def generate_products(self):
        """Generates a CSV file with mock product data with 20-dimensional feature vectors."""
        file_path = os.path.join(self.output_dir, 'products.csv')
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['product_id', 'product_name', 'category', 'price', 'features'])
            for _ in range(self.num_products):
                product_id = str(uuid.uuid4())
                self.product_ids.append(product_id)
                product_name = f"{random.choice(PRODUCT_ADJECTIVES)} {random.choice(PRODUCT_NOUNS)}"
                category = random.choice(CATEGORIES)
                price = round(random.uniform(10.0, 500.0), 2)
                features = np.random.randn(20)
                features = features / np.linalg.norm(features)
                self.product_features[product_id] = features
                features_str = json.dumps(features.tolist())
                writer.writerow([product_id, product_name, category, price, features_str])
        print(f"Successfully generated {self.num_products} products in '{file_path}'")
        return file_path

    def select_product_by_affinity(self, user_id, temperature=2.0, context_product_id=None, context_weight=0.7):
        """Selects a product based on user-product affinity."""
        user_vec = self.user_features[user_id]
        
        if context_product_id is not None and context_product_id in self.product_features:
            context_vec = self.product_features[context_product_id]
            affinities = np.array([
                context_weight * np.dot(context_vec, self.product_features[pid]) + 
                (1 - context_weight) * np.dot(user_vec, self.product_features[pid])
                for pid in self.product_ids
            ])
        else:
            affinities = np.array([np.dot(user_vec, self.product_features[pid]) for pid in self.product_ids])
        
        exp_affinities = np.exp(affinities / temperature)
        probabilities = exp_affinities / np.sum(exp_affinities)
        
        selected_product = np.random.choice(self.product_ids, p=probabilities)
        return selected_product

    def generate_clickstream(self):
        """Generates a JSON file with mock clickstream data."""
        timestamp_part = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        file_path = os.path.join(self.output_dir, f'clickstream-{timestamp_part}.json')
        stable_alias = os.path.join(self.output_dir, 'clickstream.json')

        start_time = datetime.now() - timedelta(hours=24)
        user_last_product = {}

        with open(file_path, 'w') as f:
            # Normal Activity
            for i in range(self.num_events):
                event_time = start_time + timedelta(seconds=i * 5)
                user_id = random.choice(self.user_ids)
                last_product = user_last_product.get(user_id)
                
                if last_product is not None and random.random() < 0.8:
                    product_id = self.select_product_by_affinity(user_id, context_product_id=last_product)
                else:
                    product_id = self.select_product_by_affinity(user_id)
                
                event_type = random.choice(EVENT_TYPES)
                if event_type in ['view', 'add_to_cart', 'purchase']:
                    user_last_product[user_id] = product_id
                
                event = {'timestamp': event_time.isoformat(), 'user_id': user_id, 'product_id': product_id, 'event_type': event_type}
                f.write(json.dumps(event) + '\n')

            # Fraudulent Activity
            fraud_users = random.sample(self.user_ids, 3)
            fraud_start_time = start_time + timedelta(seconds=self.num_events * 5 + 60)
            for user in fraud_users:
                fraud_context_product = None
                for i in range(15):
                    event_time = fraud_start_time + timedelta(milliseconds=i * 500)
                    if fraud_context_product is not None and random.random() < 0.6:
                        product_id = self.select_product_by_affinity(user, context_product_id=fraud_context_product, context_weight=0.5)
                    else:
                        product_id = self.select_product_by_affinity(user)
                    fraud_context_product = product_id
                    event = {'timestamp': event_time.isoformat(), 'user_id': user, 'product_id': product_id, 'event_type': 'view'}
                    f.write(json.dumps(event) + '\n')
                
                for i in range(2):
                    event_time = fraud_start_time + timedelta(milliseconds=i * 600)
                    product_id = self.select_product_by_affinity(user)
                    event = {'timestamp': event_time.isoformat(), 'user_id': user, 'product_id': product_id, 'event_type': 'payment_failed'}
                    f.write(json.dumps(event) + '\n')

        print(f"Successfully generated {self.num_events}+ events in '{file_path}'")
        try:
            shutil.copyfile(file_path, stable_alias)
            print(f"Created stable alias file: {stable_alias}")
        except Exception as e:
            print(f"Warning: Could not create stable alias file '{stable_alias}': {e}")
        
        return file_path, stable_alias

    def load_data_if_needed(self, users_file, products_file):
        """Loads user and product data from CSVs if not already generated."""
        if not self.user_ids:
            if os.path.exists(users_file):
                with open(users_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self.user_ids.append(row['user_id'])
                        self.user_features[row['user_id']] = np.array(json.loads(row['features']))
            else:
                print("Warning: No users file found. Generating users first...")
                self.generate_users()
        
        if not self.product_ids:
            if os.path.exists(products_file):
                with open(products_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self.product_ids.append(row['product_id'])
                        self.product_features[row['product_id']] = np.array(json.loads(row['features']))
            else:
                print("Warning: No products file found. Generating products first...")
                self.generate_products()


def main():
    parser = argparse.ArgumentParser(description='Generate mock ecommerce data')
    parser.add_argument('data_type', 
                       choices=['users', 'products', 'clickstream', 'all'],
                       help='Type of data to generate: users, products, clickstream, or all')
    parser.add_argument('--output-dir', '-o', 
                       default='../data',
                       help='Output directory (default: ../data)')
    parser.add_argument('--num-users', 
                       type=int, default=200,
                       help='Number of users to generate (default: 200)')
    parser.add_argument('--num-products', 
                       type=int, default=100,
                       help='Number of products to generate (default: 100)')
    parser.add_argument('--num-events', 
                       type=int, default=10000,
                       help='Number of clickstream events to generate (default: 10000)')
    parser.add_argument('--seed',
                       type=int, default=None,
                       help='Random seed for reproducible generation (default: random)')
    
    # MinIO arguments
    parser.add_argument('--upload', action='store_true', help='Upload generated data to MinIO')
    parser.add_argument('--minio-endpoint', default=os.environ.get("MINIO_ENDPOINT", "http://localhost:9000"), help="MinIO/S3 endpoint URL")
    parser.add_argument('--minio-access-key', default=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"), help="Access key")
    parser.add_argument('--minio-secret-key', default=os.environ.get("MINIO_SECRET_KEY", "minioadmin"), help="Secret key")
    parser.add_argument('--minio-bucket', default=os.environ.get("DATA_BUCKET", "warehouse"), help="Target bucket")
    
    args = parser.parse_args()

    generator = DataGenerator(
        num_users=args.num_users,
        num_products=args.num_products,
        num_events=args.num_events,
        output_dir=args.output_dir,
        seed=args.seed
    )

    users_file = os.path.join(args.output_dir, 'users.csv')
    products_file = os.path.join(args.output_dir, 'products.csv')
    clickstream_file = None
    stable_clickstream_alias = None

    if args.data_type in ['users', 'all']:
        users_file = generator.generate_users()
    
    if args.data_type in ['products', 'all']:
        products_file = generator.generate_products()
    
    if args.data_type in ['clickstream', 'all']:
        generator.load_data_if_needed(users_file, products_file)
        clickstream_file, stable_clickstream_alias = generator.generate_clickstream()

    if args.upload:
        if clickstream_file is None:
             # Handle case where only users/products are generated and need uploading
            timestamp_part = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            clickstream_file = os.path.join(args.output_dir, f'clickstream-{timestamp_part}.json') # a bit of a hack
            stable_clickstream_alias = os.path.join(args.output_dir, 'clickstream.json')

        upload_generated_data(args, users_file, products_file, clickstream_file, stable_clickstream_alias)

    print(f"\nMock data generation complete for: {args.data_type}")


def setup_minio_client(endpoint, access_key, secret_key):
    """Create and configure MinIO client."""
    return boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
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

def upload_generated_data(args, users_file, products_file, clickstream_file, stable_clickstream_alias):
    """Upload generated data to MinIO."""
    print("\n🚀 Uploading data artifacts to MinIO/S3...")
    try:
        s3_client = setup_minio_client(args.minio_endpoint, args.minio_access_key, args.minio_secret_key)
        print("✅ MinIO/S3 client configured")
        create_bucket_if_not_exists(s3_client, args.minio_bucket)
    except Exception as e:
        print(f"❌ Failed to configure client or create bucket: {e}")
        return

    prefix = "data"
    success_count = 0

    if os.path.exists(users_file):
        if upload_file_to_minio(s3_client, users_file, args.minio_bucket, f"{prefix}/users.csv"):
            success_count += 1
    
    if os.path.exists(products_file):
        if upload_file_to_minio(s3_client, products_file, args.minio_bucket, f"{prefix}/products.csv"):
            success_count += 1

    if os.path.exists(clickstream_file):
        filename = os.path.basename(clickstream_file)
        individual_key = f"{prefix}/clickstream/individual/{filename}"
        stable_key = f"{prefix}/clickstream/clickstream.json"
        
        if upload_file_to_minio(s3_client, clickstream_file, args.minio_bucket, individual_key):
            success_count += 1
        
        if os.path.exists(stable_clickstream_alias):
            if upload_file_to_minio(s3_client, stable_clickstream_alias, args.minio_bucket, stable_key):
                success_count += 1
                print(f"✅ Stable alias uploaded: s3://{args.minio_bucket}/{stable_key}")
    
    print(f"\n📊 Upload Summary: Total successful uploads: {success_count}")


if __name__ == '__main__':
    main()

