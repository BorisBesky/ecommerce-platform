import csv
import json
import os
import random
import uuid
from datetime import datetime, timedelta

# --- Configuration ---
NUM_USERS = 200
NUM_PRODUCTS = 100
NUM_EVENTS = 10000
OUTPUT_DIR = '../data'

# --- Sample Data ---
FIRST_NAMES = ['John', 'Jane', 'Peter', 'Mary', 'Chris', 'Pat', 'Alex', 'Sam', 'Taylor', 'Jordan']
LAST_NAMES = ['Smith', 'Jones', 'Williams', 'Brown', 'Davis', 'Miller', 'Wilson', 'Moore', 'Taylor', 'Anderson']
PRODUCT_NOUNS = ['Keyboard', 'Mouse', 'Monitor', 'Chair', 'Desk', 'Webcam', 'Headset', 'Laptop', 'Dock', 'Cable']
PRODUCT_ADJECTIVES = ['Ergonomic', 'Mechanical', 'Gaming', 'Wireless', '4K', 'Curved', 'Standing', 'Adjustable', 'HD']
CATEGORIES = ['Electronics', 'Office', 'Peripherals', 'Furniture', 'Accessories']
EVENT_TYPES = ['view', 'view', 'view', 'view', 'add_to_cart', 'add_to_cart', 'purchase', 'payment_failed']


def generate_users(file_path):
    """Generates a CSV file with mock user data."""
    user_ids = []
    with open(file_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['user_id', 'name', 'signup_date'])
        for _ in range(NUM_USERS):
            user_id = str(uuid.uuid4())
            user_ids.append(user_id)
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            signup_date = (datetime.now() - timedelta(days=random.randint(1, 365))).strftime('%Y-%m-%d')
            writer.writerow([user_id, name, signup_date])
    print(f"Successfully generated {NUM_USERS} users in '{file_path}'")
    return user_ids

def generate_products(file_path):
    """Generates a CSV file with mock product data."""
    product_ids = []
    with open(file_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['product_id', 'product_name', 'category', 'price'])
        for _ in range(NUM_PRODUCTS):
            product_id = str(uuid.uuid4())
            product_ids.append(product_id)
            product_name = f"{random.choice(PRODUCT_ADJECTIVES)} {random.choice(PRODUCT_NOUNS)}"
            category = random.choice(CATEGORIES)
            price = round(random.uniform(10.0, 500.0), 2)
            writer.writerow([product_id, product_name, category, price])
    print(f"Successfully generated {NUM_PRODUCTS} products in '{file_path}'")
    return product_ids

def generate_clickstream(file_path, user_ids, product_ids):
    """
    Generates a JSON file with mock clickstream data.
    Each line in the file is a separate JSON object.
    """
    start_time = datetime.now() - timedelta(hours=24)

    with open(file_path, 'w') as f:
        # --- Normal Activity ---
        for i in range(NUM_EVENTS):
            event_time = start_time + timedelta(seconds=i * 5) # Events every 5 seconds
            event = {
                'timestamp': event_time.isoformat(),
                'user_id': random.choice(user_ids),
                'product_id': random.choice(product_ids),
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
                event = {
                    'timestamp': event_time.isoformat(),
                    'user_id': user,
                    'product_id': random.choice(product_ids),
                    'event_type': 'view' # Rapid views are a common fraud pattern
                }
                f.write(json.dumps(event) + '\n')
            # Add a couple of failed payments for good measure
            for i in range(2):
                 event_time = fraud_start_time + timedelta(milliseconds=i * 600)
                 event = {
                    'timestamp': event_time.isoformat(),
                    'user_id': user,
                    'product_id': random.choice(product_ids),
                    'event_type': 'payment_failed'
                }
                 f.write(json.dumps(event) + '\n')


    print(f"Successfully generated {NUM_EVENTS}+ events in '{file_path}'")


if __name__ == '__main__':
    # Create the output directory if it doesn't exist
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Created directory: '{OUTPUT_DIR}'")

    users_file = os.path.join(OUTPUT_DIR, 'users.csv')
    products_file = os.path.join(OUTPUT_DIR, 'products.csv')
    clickstream_file = os.path.join(OUTPUT_DIR, 'clickstream.json')

    user_ids = generate_users(users_file)
    product_ids = generate_products(products_file)
    generate_clickstream(clickstream_file, user_ids, product_ids)

    print("\nMock data generation complete.")

