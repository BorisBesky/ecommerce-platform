import argparse
import csv
import json
import os
import random
import uuid
from datetime import datetime, timedelta
import shutil
import numpy as np

# --- Sample Data ---
FIRST_NAMES = ['John', 'Jane', 'Peter', 'Mary', 'Chris', 'Pat', 'Alex', 'Sam', 'Taylor', 'Jordan']
LAST_NAMES = ['Smith', 'Jones', 'Williams', 'Brown', 'Davis', 'Miller', 'Wilson', 'Moore', 'Taylor', 'Anderson']
PRODUCT_NOUNS = ['Keyboard', 'Mouse', 'Monitor', 'Chair', 'Desk', 'Webcam', 'Headset', 'Laptop', 'Dock', 'Cable']
PRODUCT_ADJECTIVES = ['Ergonomic', 'Mechanical', 'Gaming', 'Wireless', '4K', 'Curved', 'Standing', 'Adjustable', 'HD']
CATEGORIES = ['Electronics', 'Office', 'Peripherals', 'Furniture', 'Accessories']
EVENT_TYPES = ['view', 'view', 'view', 'view', 'add_to_cart', 'add_to_cart', 'purchase', 'payment_failed']


def generate_users(file_path):
    """Generates a CSV file with mock user data with 10-dimensional feature vectors."""
    user_ids = []
    user_features = {}
    with open(file_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['user_id', 'name', 'signup_date', 'features'])
        for _ in range(NUM_USERS):
            user_id = str(uuid.uuid4())
            user_ids.append(user_id)
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            signup_date = (datetime.now() - timedelta(days=random.randint(1, 365))).strftime('%Y-%m-%d')
            # Generate 10-dimensional feature vector (normalized)
            features = np.random.randn(10)
            features = features / np.linalg.norm(features)  # Normalize to unit vector
            user_features[user_id] = features
            # Store as JSON string
            features_str = json.dumps(features.tolist())
            writer.writerow([user_id, name, signup_date, features_str])
    print(f"Successfully generated {NUM_USERS} users in '{file_path}'")
    return user_ids, user_features

def generate_products(file_path):
    """Generates a CSV file with mock product data with 10-dimensional feature vectors."""
    product_ids = []
    product_features = {}
    with open(file_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['product_id', 'product_name', 'category', 'price', 'features'])
        for _ in range(NUM_PRODUCTS):
            product_id = str(uuid.uuid4())
            product_ids.append(product_id)
            product_name = f"{random.choice(PRODUCT_ADJECTIVES)} {random.choice(PRODUCT_NOUNS)}"
            category = random.choice(CATEGORIES)
            price = round(random.uniform(10.0, 500.0), 2)
            # Generate 10-dimensional feature vector (normalized)
            features = np.random.randn(10)
            features = features / np.linalg.norm(features)  # Normalize to unit vector
            product_features[product_id] = features
            # Store as JSON string
            features_str = json.dumps(features.tolist())
            writer.writerow([product_id, product_name, category, price, features_str])
    print(f"Successfully generated {NUM_PRODUCTS} products in '{file_path}'")
    return product_ids, product_features

def select_product_by_affinity(user_id, user_features, product_ids, product_features, temperature=2.0):
    """
    Select a product based on affinity between user and product feature vectors.
    Uses softmax with temperature to convert dot products into probabilities.
    
    Higher temperature = more random, lower temperature = more deterministic
    """
    user_vec = user_features[user_id]
    
    # Compute affinity scores (dot product since vectors are normalized)
    affinities = np.array([np.dot(user_vec, product_features[pid]) for pid in product_ids])
    
    # Apply softmax with temperature
    exp_affinities = np.exp(affinities / temperature)
    probabilities = exp_affinities / np.sum(exp_affinities)
    
    # Sample product based on probabilities
    selected_product = np.random.choice(product_ids, p=probabilities)
    return selected_product


def generate_clickstream(file_path, user_ids, product_ids, user_features, product_features):
    """
    Generates a JSON file with mock clickstream data based on user-product affinity.
    Each line in the file is a separate JSON object.
    """
    start_time = datetime.now() - timedelta(hours=24)

    with open(file_path, 'w') as f:
        # --- Normal Activity ---
        for i in range(NUM_EVENTS):
            event_time = start_time + timedelta(seconds=i * 5) # Events every 5 seconds
            user_id = random.choice(user_ids)
            # Select product based on affinity with user
            product_id = select_product_by_affinity(user_id, user_features, product_ids, product_features)
            event = {
                'timestamp': event_time.isoformat(),
                'user_id': user_id,
                'product_id': product_id,
                'event_type': random.choice(EVENT_TYPES)
            }
            f.write(json.dumps(event) + '\n')

        # --- Fraudulent Activity Simulation ---
        # Pick 3 users to be our "fraudsters"
        fraud_users = random.sample(user_ids, 3)
        print(f"\nSimulating fraud activity for users: {', '.join(fraud_users)}")
        fraud_start_time = start_time + timedelta(seconds=NUM_EVENTS * 5 + 60)

        for user in fraud_users:
            # Generate 15 rapid-fire events for each fraudster within a 10-second window
            for i in range(15):
                event_time = fraud_start_time + timedelta(milliseconds=i * 500) # Fast clicks
                # Fraud uses affinity-based selection too
                product_id = select_product_by_affinity(user, user_features, product_ids, product_features)
                event = {
                    'timestamp': event_time.isoformat(),
                    'user_id': user,
                    'product_id': product_id,
                    'event_type': 'view' # Rapid views are a common fraud pattern
                }
                f.write(json.dumps(event) + '\n')
            # Add a couple of failed payments for good measure
            for i in range(2):
                 event_time = fraud_start_time + timedelta(milliseconds=i * 600)
                 product_id = select_product_by_affinity(user, user_features, product_ids, product_features)
                 event = {
                    'timestamp': event_time.isoformat(),
                    'user_id': user,
                    'product_id': product_id,
                    'event_type': 'payment_failed'
                }
                 f.write(json.dumps(event) + '\n')


    print(f"Successfully generated {NUM_EVENTS}+ events in '{file_path}'")


def main():
    global NUM_USERS, NUM_PRODUCTS, NUM_EVENTS, OUTPUT_DIR
    NUM_USERS = 200
    NUM_PRODUCTS = 100
    NUM_EVENTS = 10000
    OUTPUT_DIR = '../data'
    
    parser = argparse.ArgumentParser(description='Generate mock ecommerce data')
    parser.add_argument('data_type', 
                       choices=['users', 'products', 'clickstream', 'all'],
                       help='Type of data to generate: users, products, clickstream, or all')
    parser.add_argument('--output-dir', '-o', 
                       default=OUTPUT_DIR,  # Now we can reference the global
                       help=f'Output directory (default: {OUTPUT_DIR})')
    parser.add_argument('--num-users', 
                       type=int, default=NUM_USERS,  # Reference the global
                       help=f'Number of users to generate (default: {NUM_USERS})')
    parser.add_argument('--num-products', 
                       type=int, default=NUM_PRODUCTS,  # Reference the global
                       help=f'Number of products to generate (default: {NUM_PRODUCTS})')
    parser.add_argument('--num-events', 
                       type=int, default=NUM_EVENTS,  # Reference the global
                       help=f'Number of clickstream events to generate (default: {NUM_EVENTS})')
    parser.add_argument('--seed',
                       type=int, default=None,
                       help='Random seed for reproducible generation (default: random)')
    
    args = parser.parse_args()
    
    NUM_USERS = args.num_users
    NUM_PRODUCTS = args.num_products
    NUM_EVENTS = args.num_events
    OUTPUT_DIR = args.output_dir

    # Apply seed if provided
    if args.seed is not None:
        random.seed(args.seed)
        try:
            import numpy as _np
            _np.random.seed(args.seed)
        except Exception:
            pass
        print(f"Using random seed: {args.seed}")
    
    # Create the output directory if it doesn't exist
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Created directory: '{OUTPUT_DIR}'")

    users_file = os.path.join(OUTPUT_DIR, 'users.csv')
    products_file = os.path.join(OUTPUT_DIR, 'products.csv')
    timestamp_part = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    clickstream_file = os.path.join(OUTPUT_DIR, f'clickstream-{timestamp_part}.json')
    stable_clickstream_alias = os.path.join(OUTPUT_DIR, 'clickstream.json')

    user_ids = []
    product_ids = []
    user_features = {}
    product_features = {}

    if args.data_type in ['users', 'all']:
        user_ids, user_features = generate_users(users_file)
    
    if args.data_type in ['products', 'all']:
        product_ids, product_features = generate_products(products_file)
    
    if args.data_type in ['clickstream', 'all']:
        # For clickstream generation, we need user and product IDs with features
        if not user_ids:
            # Load existing user IDs and features if they weren't just generated
            if os.path.exists(users_file):
                with open(users_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        user_ids.append(row['user_id'])
                        user_features[row['user_id']] = np.array(json.loads(row['features']))
            else:
                print("Warning: No users file found. Generating users first...")
                user_ids, user_features = generate_users(users_file)
        
        if not product_ids:
            # Load existing product IDs and features if they weren't just generated
            if os.path.exists(products_file):
                with open(products_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        product_ids.append(row['product_id'])
                        product_features[row['product_id']] = np.array(json.loads(row['features']))
            else:
                print("Warning: No products file found. Generating products first...")
                product_ids, product_features = generate_products(products_file)
        
        generate_clickstream(clickstream_file, user_ids, product_ids, user_features, product_features)
        # Maintain a stable alias file for downstream jobs expecting clickstream.json
        try:
            shutil.copyfile(clickstream_file, stable_clickstream_alias)
            print(f"Created stable alias file: {stable_clickstream_alias}")
        except Exception as e:
            print(f"Warning: Could not create stable alias file '{stable_clickstream_alias}': {e}")

    print(f"\nMock data generation complete for: {args.data_type}")


if __name__ == '__main__':
    main()

