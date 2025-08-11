import ray
import pandas as pd
import json
import boto3
from botocore.config import Config

# --- Configuration ---
# Connection details for our Docker services
RAY_ADDRESS = "ray://ray-head:10001"
CATALOG_NAME = "nessie"
MINIO_ENDPOINT = "http://minio:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
S3_BUCKET = "warehouse"
OUTPUT_FILE_KEY = "models/legitimate_user_profile.json" # Path within the bucket

def main():
    """
    Main Ray application to analyze user data from Iceberg, process it in a
    distributed manner, and save the results.
    """
    try:
        # 1. Initialize Ray and Connect to the Cluster
        # =================================================================
        # We connect to the Ray head node using its service name and client port.
        print(f"Initializing Ray and connecting to cluster at {RAY_ADDRESS}...")
        ray.init(address=RAY_ADDRESS, ignore_reinit_error=True)
        print("Successfully connected to Ray cluster.")
        print("Cluster resources:", ray.cluster_resources())

        # 2. Load Data from Iceberg into Ray Datasets
        # =================================================================
        # Ray Data can read directly from Iceberg tables using the same catalog info.
        # We need to provide an S3-compatible filesystem object so Ray knows how
        # to access the data files in MinIO.
        from pyarrow.fs import S3FileSystem
        s3 = S3FileSystem(
            endpoint_override=MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            scheme="http",
            allow_bucket_creation=True # Important for some environments
        )

        print("Loading 'fraud_attempts' table from Iceberg...")
        fraud_ds = ray.data.read_iceberg(
            catalog_name=CATALOG_NAME,
            table_name="demo.fraud_attempts",
            filesystem=s3
        )
        
        print("Loading 'users' table from Iceberg...")
        users_ds = ray.data.read_iceberg(
            catalog_name=CATALOG_NAME,
            table_name="demo.users",
            filesystem=s3
        )
        print("Data loaded successfully into Ray Datasets.")

        # 3. Process Data in a Distributed Fashion
        # =================================================================
        # Our goal: Profile our 'good' users by counting signups per month.
        
        # First, get a list of all fraudulent user IDs.
        # This is a small dataset, so we can collect it to the head node.
        fraud_user_ids = set(fraud_ds.to_pandas()["user_id"].unique())
        print(f"Found {len(fraud_user_ids)} fraudulent user IDs.")
        
        # Broadcast the set of fraudulent IDs to all worker nodes efficiently.
        fraud_ids_ref = ray.put(fraud_user_ids)

        # Define a function to process batches of user data.
        # This function will be executed in parallel on different nodes.
        def filter_and_transform_users(batch: pd.DataFrame) -> pd.DataFrame:
            # Retrieve the broadcasted set of fraudulent IDs.
            fraud_ids = ray.get(fraud_ids_ref)
            
            # Filter out fraudulent users.
            good_users_batch = batch[~batch["user_id"].isin(fraud_ids)]
            
            # Create a new column for the signup month (e.g., '2025-08').
            good_users_batch["signup_month"] = pd.to_datetime(good_users_batch["signup_date"]).dt.strftime('%Y-%m')
            
            return good_users_batch[["signup_month"]]

        print("Applying distributed transformation to filter users and extract signup month...")
        # Use map_batches to apply our function across the dataset in parallel.
        monthly_signups_ds = users_ds.map_batches(filter_and_transform_users)

        # Perform a distributed aggregation (groupby and count).
        print("Performing distributed aggregation to count signups per month...")
        signup_counts = monthly_signups_ds.groupby("signup_month").count().to_pandas()
        
        print("\n--- Analysis Result ---")
        print(signup_counts)
        print("-----------------------\n")

        # 4. Save the Result to MinIO
        # =================================================================
        print(f"Saving results to S3 bucket '{S3_BUCKET}' at '{OUTPUT_FILE_KEY}'...")
        
        # Convert the final pandas DataFrame to a JSON string.
        result_json = signup_counts.to_json(orient="records")

        # Use boto3 to connect to MinIO and upload the file.
        s3_client = boto3.client(
            's3',
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            config=Config(signature_version='s3v4')
        )
        
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=OUTPUT_FILE_KEY,
            Body=result_json.encode('utf-8'),
            ContentType='application/json'
        )
        print("Result saved successfully.")

    except Exception as e:
        print(f"An error occurred during the Ray job: {e}")
    finally:
        print("Shutting down Ray connection.")
        ray.shutdown()

if __name__ == "__main__":
    main()
