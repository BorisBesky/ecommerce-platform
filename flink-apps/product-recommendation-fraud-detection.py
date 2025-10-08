import os
import random
import requests
import json
from pyflink.table import (
    DataTypes,
    StreamTableEnvironment,
    Schema,
    TableDescriptor,
    expressions as expr
)
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.table.expressions import col, lit
from pyflink.table.window import Tumble
from pyflink.table.udf import udtf

# --- Configuration ---
CATALOG_NAME = "nessie"
DATABASE_NAME = "demo"
NESSIE_URI = "http://nessie:19120/api/v1"
WAREHOUSE_PATH = "s3a://warehouse"
MINIO_ENDPOINT = "http://minio:9000"
SOURCE_DATA_PATH = "/data"
# Ray Serve endpoint for recommendations
RAY_SERVE_ENDPOINT = os.environ.get(
    "RAY_SERVE_ENDPOINT",
    "http://recommendation-service-serve-svc.ecommerce-platform.svc.cluster.local:8000"
)

# --- Real Recommendation Logic via Ray Serve ---
@udtf(result_types=[DataTypes.STRING(), DataTypes.DOUBLE()])
def get_recommendations(user_id: str, product_id: str):
    """
    Call Ray Serve endpoint to get real recommendations for a user.
    
    Args:
        user_id: The user to get recommendations for
        product_id: The product they're currently viewing (used for exclusion)
    
    Yields:
        Tuples of (recommended_product_id, score)
    """
    try:
        # Call Ray Serve endpoint
        url = f"{RAY_SERVE_ENDPOINT}/recommend"
        payload = {
            "user_id": user_id,
            "n": 5,  # Get top 5 recommendations
            "exclude_products": [product_id]  # Exclude current product
        }
        
        response = requests.post(
            url,
            json=payload,
            timeout=2.0  # 2 second timeout
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # Check for errors in response
            if "error" in result:
                print(f"Error from recommendation service: {result['error']}")
                # Return empty - no recommendations
                return
            
            # Yield each recommendation
            recommendations = result.get("recommendations", [])
            for rec in recommendations:
                yield rec["product_id"], rec["score"]
        else:
            print(f"Recommendation service returned status {response.status_code}")
            # Return empty - service unavailable
            return
            
    except requests.exceptions.Timeout:
        print(f"Timeout calling recommendation service for user {user_id}")
        return
    except Exception as e:
        print(f"Error getting recommendations for user {user_id}: {e}")
        return

def main():
    """
    Flink streaming job that integrates fraud detection with real-time
    recommendation generation.
    """
    env = StreamExecutionEnvironment.get_execution_environment()
    t_env = StreamTableEnvironment.create(stream_execution_environment=env)

    # Set up JARs and Catalog (same as before)
    t_env.get_config().set(
        "pipeline.jars",
        "file:///flink-jars/iceberg-flink-runtime-1.4.3.jar;"
        "file:///flink-jars/hadoop-common-3.3.4.jar;"
        "file:///flink-jars/hadoop-aws-3.3.4.jar;"
        "file:///flink-jars/aws-java-sdk-bundle-1.12.665.jar"
    )
    
    # Configure Hadoop S3A settings for MinIO
    t_env.get_config().set("fs.s3a.endpoint", "http://minio:9000")
    t_env.get_config().set("fs.s3a.access.key", "minioadmin")
    t_env.get_config().set("fs.s3a.secret.key", "minioadmin")
    t_env.get_config().set("fs.s3a.path.style.access", "true")
    t_env.get_config().set("fs.s3a.ssl.enabled", "false")
    t_env.get_config().set("fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")

    t_env.execute_sql(f"""
    CREATE CATALOG {CATALOG_NAME} WITH (
        'type'='iceberg', 'catalog-impl'='org.apache.iceberg.nessie.NessieCatalog',
        'uri'='{NESSIE_URI}', 'ref'='main', 'authentication.type'='none',
        'warehouse'='{WAREHOUSE_PATH}', 'io-impl'='org.apache.iceberg.aws.s3.S3FileIO',
        's3.endpoint'='{MINIO_ENDPOINT}',
        's3.path-style-access'='true',
        's3.ssl.enabled'='false'
    )""")
    t_env.use_catalog(CATALOG_NAME)
    
    # Create the database if it doesn't exist
    try:
        t_env.execute_sql(f"CREATE DATABASE IF NOT EXISTS {DATABASE_NAME}")
    except Exception as e:
        print(f"Database creation warning (might already exist): {e}")
    
    t_env.use_database(DATABASE_NAME)
    
    # Register the User-Defined Table Function
    t_env.create_temporary_function("get_recommendations", get_recommendations)

    source_descriptor = (
        TableDescriptor.for_connector("filesystem")
        .schema(
            Schema.new_builder()
            .column("user_id", DataTypes.STRING())
            .column("product_id", DataTypes.STRING())
            .column("event_type", DataTypes.STRING())
            # Define 'timestamp' field from JSON as a string initially
            .column("timestamp", DataTypes.STRING())
            # Create a computed column for the event time
            .column_by_expression("event_time", "TO_TIMESTAMP(`timestamp`, 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS')")
            # Define the watermark strategy on the event_time column
            .watermark("event_time", "event_time - INTERVAL '5' SECOND")
            .build()
        )
        # Monitor the data dir, but only match top-level clickstream JSON files to avoid nested dirs
        .option("path", SOURCE_DATA_PATH)
        # Process all existing files
        .option("source.path.regex-pattern", ".*clickstream.*\\.json")
            .option("json.ignore-parse-errors", "true")
            .format("json")
            .build()
        )
    
    source_table = t_env.from_descriptor(source_descriptor)

    table_exists = t_env.execute_sql("SHOW TABLES").collect()
    if ("fraud_attempts",) in table_exists:
        print("Table 'fraud_attempts' already exists.")
    else:
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS fraud_attempts (
            user_id STRING,
            window_start TIMESTAMP(3),
            window_end TIMESTAMP(3),
            event_count BIGINT
        ) WITH (
            'format-version' = '2'
        )
        """
        t_env.execute_sql(create_table_sql)
        print("Table 'fraud_attempts' created successfully.")


    # --- 1. Fraud Detection Sink  ---
    fraud_attempts = (
        source_table.window(Tumble.over(lit(10).seconds).on(col("event_time")).alias("w"))
        .group_by(col("w"), col("user_id"))
        .select(
            col("user_id"),
            col("w").start.alias("window_start"),
            col("w").end.alias("window_end"),
            col("user_id").count.alias("event_count"),
        )
        .where(col("event_count") > 5)
    )
    
    # Now insert the results from our query
    print("Submitting job to write to Iceberg table 'demo.fraud_attempts'...")
    fraud_attempts.execute_insert("fraud_attempts")

    # --- 2. Real-Time Recommendation Sink (New) ---
    # Process all events for recommendations
    # In a real scenario, we might want to implement fraud filtering differently
    
    # Use the UDTF to generate recommendations for each event
    # The LATERAL TABLE join allows us to call the function for each row.
    recommendations = source_table.flat_map(expr.call("get_recommendations", col("user_id"), col("product_id"))) \
                                  .alias("recommendation_type", "recommended_product_id")

    # Add the user_id back to the final output
    recommendations_with_user = source_table.join(
            recommendations,
            expr.lit(True) # This is a trick for a 1-to-many join with a UDTF
        ).select(
            col("user_id"),
            col("recommendation_type"),
            col("recommended_product_id")
        )

    # Create and sink to the new recommendations table
    t_env.execute_sql("""
        CREATE TABLE IF NOT EXISTS user_recommendations (
            user_id STRING,
            recommendation_type STRING,
            recommended_product_id STRING
        ) WITH ('format-version'='2')
    """)
    recommendations_with_user.execute_insert("user_recommendations")
    print("Recommendation generation sink configured.")

    # The overall job will now run both sinks in parallel.
    print("Submitted combined fraud and recommendation job...")

if __name__ == "__main__":
    main()
