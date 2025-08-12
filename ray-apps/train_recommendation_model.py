import ray
import pandas as pd
import boto3
import pickle
from botocore.config import Config

# Import ML libraries for the training job
# We will use scikit-surprise directly, as the Ray Train wrapper has been removed.
from surprise import Dataset, Reader, SVD
from surprise.model_selection import train_test_split
from surprise import accuracy

# --- Configuration ---
RAY_ADDRESS = "ray://ray-head:10001"
# NOTE: We are not reading from Iceberg in this version to simplify the training logic,
# but the principle of loading data first remains the same.
MINIO_ENDPOINT = "http://minio:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
S3_BUCKET = "warehouse"
OUTPUT_MODEL_KEY = "models/recommendation_model.pkl"
# This assumes the 'data' directory is mounted at /data in the Ray container.
CLICKSTREAM_DATA_PATH = "/data/clickstream.json"

def main():
    """
    Main Ray application to train a collaborative filtering recommendation model
    and save the artifact to S3.
    """
    try:
        # 1. Initialize Ray and Connect to the Cluster
        # =================================================================
        print(f"Initializing Ray and connecting to cluster at {RAY_ADDRESS}...")
        # We connect to the cluster to show orchestration, even if training is local.
        ray.init(address=RAY_ADDRESS, ignore_reinit_error=True)
        print("Successfully connected to Ray cluster.")

        # 2. Load and Prepare Data for Training
        # =================================================================
        # For this example, we'll read the local JSON. In a production scenario,
        # you would use ray.data to read from an Iceberg table here.
        print(f"Loading 'clickstream' data from {CLICKSTREAM_DATA_PATH}...")
        clickstream_df = pd.read_json(CLICKSTREAM_DATA_PATH, lines=True)
        
        # --- Feature Engineering: Create user-item "ratings" ---
        event_weights = {
            'view': 1.0,
            'add_to_cart': 3.0,
            'purchase': 5.0,
            'payment_failed': -2.0
        }
        clickstream_df['rating'] = clickstream_df['event_type'].map(event_weights)
        
        ratings_df = clickstream_df.groupby(['user_id', 'product_id'])['rating'].sum().reset_index()
        print(f"Created {len(ratings_df)} user-item ratings from clickstream data.")

        # 3. Train the Recommendation Model (Directly with Surprise)
        # =================================================================
        print("Preparing data for scikit-surprise...")
        reader = Reader(rating_scale=(ratings_df['rating'].min(), ratings_df['rating'].max()))
        data = Dataset.load_from_df(ratings_df[['user_id', 'product_id', 'rating']], reader)
        
        # Split data into training and testing sets
        trainset, testset = train_test_split(data, test_size=0.2)

        # Define and train the SVD algorithm
        print("Training SVD model directly...")
        algo = SVD(
            n_epochs=10,
            lr_all=0.005,
            reg_all=0.02,
            verbose=True
        )
        algo.fit(trainset)
        
        # Evaluate the model
        predictions = algo.test(testset)
        rmse = accuracy.rmse(predictions)

        print("\n--- Training Result ---")
        print(f"Training finished. Final model accuracy (RMSE): {rmse:.4f}")
        print("-----------------------\n")
        
        # The trained model is the 'algo' object itself
        trained_model = algo

        # 4. Save the Trained Model to MinIO
        # =================================================================
        print(f"Saving trained model to S3 bucket '{S3_BUCKET}' at '{OUTPUT_MODEL_KEY}'...")
        
        model_bytes = pickle.dumps(trained_model)

        s3_client = boto3.client(
            's3',
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_key=MINIO_SECRET_KEY,
            config=Config(signature_version='s3v4')
        )
        
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=OUTPUT_MODEL_KEY,
            Body=model_bytes
        )
        print("Model artifact saved successfully.")

    except Exception as e:
        print(f"An error occurred during the Ray job: {e}")
    finally:
        print("Shutting down Ray connection.")
        ray.shutdown()

if __name__ == "__main__":
    main()
