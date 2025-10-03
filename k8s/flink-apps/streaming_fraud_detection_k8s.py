import os
from pyflink.table import (
    DataTypes,
    StreamTableEnvironment,
    Schema,
    TableDescriptor,
)
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.table.expressions import col, lit
from pyflink.table.window import Tumble

# Define configuration for Kubernetes services
CATALOG_NAME = "nessie"
DATABASE_NAME = "demo"
NESSIE_URI = "http://nessie.ecommerce-platform.svc.cluster.local:19120/api/v1"
WAREHOUSE_PATH = "s3a://warehouse"
MINIO_ENDPOINT = "http://minio.ecommerce-platform.svc.cluster.local:9000"

# Optional staged clickstream path (JSON lines) in MinIO via S3A exposed through catalog / direct filesystem
# Use wildcard to read all individual clickstream files
STAGED_CLICKSTREAM_JSON = "s3a://warehouse/data/clickstream/individual/"

def main():
    """
    Main Flink streaming job for real-time fraud detection in Kubernetes.
    """
    # 1. Set up the streaming environment
    # ===============================================================
    env = StreamExecutionEnvironment.get_execution_environment()
    # Ensure periodic checkpoints so Iceberg commits data (commits happen on checkpoints)
    env.enable_checkpointing(10000)  # 10s

    t_env = StreamTableEnvironment.create(stream_execution_environment=env)

    # Also set runtime and checkpoint settings via Table API configuration
    cfg = t_env.get_config().get_configuration()
    cfg.set_string("execution.runtime-mode", "STREAMING")
    cfg.set_string("execution.checkpointing.mode", "EXACTLY_ONCE")
    cfg.set_string("execution.checkpointing.interval", "10 s")
    # Use a local checkpoint directory inside the container
    cfg.set_string("state.checkpoints.dir", "file:///tmp/flink-checkpoints")

    print("Flink streaming environment initialized for Kubernetes deployment.")

    # Configure S3A settings for MinIO
    # ===============================================================
    cfg.set_string("fs.s3a.endpoint", MINIO_ENDPOINT)
    cfg.set_string("fs.s3a.access.key", "minioadmin")
    cfg.set_string("fs.s3a.secret.key", "minioadmin")
    cfg.set_string("fs.s3a.path.style.access", "true")
    cfg.set_string("fs.s3a.ssl.enabled", "false")
    cfg.set_string("fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
    
    # Also set via table environment configuration
    t_env.get_config().set("fs.s3a.endpoint", MINIO_ENDPOINT)
    t_env.get_config().set("fs.s3a.access.key", "minioadmin")
    t_env.get_config().set("fs.s3a.secret.key", "minioadmin")
    t_env.get_config().set("fs.s3a.path.style.access", "true")
    t_env.get_config().set("fs.s3a.ssl.enabled", "false")
    t_env.get_config().set("fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
    
    print("S3A configuration set for MinIO.")

    # 2. Create the Nessie Iceberg Catalog
    # ===============================================================
    # This registers our Nessie catalog so Flink knows how to interact with it.
    create_catalog_sql = f"""
    CREATE CATALOG {CATALOG_NAME}
    WITH (
        'type'='iceberg',
        'catalog-impl'='org.apache.iceberg.nessie.NessieCatalog',
        'uri'='{NESSIE_URI}',
        'ref'='main',
        'authentication.type'='none',
        'warehouse'='{WAREHOUSE_PATH}',
        'io-impl'='org.apache.iceberg.aws.s3.S3FileIO',
        's3.endpoint'='{MINIO_ENDPOINT}',
        's3.path-style-access'='true',
        's3.access-key-id'='minioadmin',
        's3.secret-access-key'='minioadmin',
        's3.region'='us-east-1',
        'nessie.client.http.compression.enabled'='false'
    )
    """
    
    print("Creating Nessie catalog...")
    t_env.execute_sql(create_catalog_sql)
    print("Nessie catalog created successfully.")
    t_env.use_catalog(CATALOG_NAME)

    # 3. Create database if it doesn't exist
    # ===============================================================
    print(f"Creating database '{DATABASE_NAME}' if it doesn't exist...")
    t_env.execute_sql(f"CREATE DATABASE IF NOT EXISTS {DATABASE_NAME}")
    t_env.use_database(DATABASE_NAME)
    
    # 4. Create temporary source table for clickstream events using filesystem connector
    # ===============================================================
    # Note: We can't use computed columns with Iceberg catalog, so we use a temporary table
    # with the default_catalog for the filesystem source.
    print("Creating clickstream source table...")
    
    t_env.use_catalog("default_catalog")
    t_env.use_database("default_database")
    
    create_source_sql = f"""
    CREATE TEMPORARY TABLE IF NOT EXISTS clickstream_events (
        user_id STRING,
        product_id STRING,
        event_type STRING,
        `timestamp` STRING,
        event_time AS TO_TIMESTAMP(
            SUBSTRING(REPLACE(`timestamp`, 'T', ' '), 1, 23)
        ),
        WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
    ) WITH (
        'connector' = 'filesystem',
        'path' = '{STAGED_CLICKSTREAM_JSON}',
        'format' = 'json',
        'json.ignore-parse-errors' = 'true',
        'source.monitor-interval' = '1000'
    )
    """
    
    t_env.execute_sql(create_source_sql)
    print("Clickstream source table created.")
    
    # Switch back to Nessie catalog for sink table
    t_env.use_catalog(CATALOG_NAME)
    t_env.use_database(DATABASE_NAME)

    # 5. Create fraud detection logic using SQL
    # ===============================================================
    print("Setting up fraud detection logic...")
    
    # Create a view for fraud detection using SQL window functions
    # Note: Must use fully qualified table name since source is in default_catalog
    fraud_detection_sql = f"""
    CREATE TEMPORARY VIEW fraud_events AS
    SELECT 
        user_id,
        TUMBLE_START(event_time, INTERVAL '10' SECOND) as window_start,
        TUMBLE_END(event_time, INTERVAL '10' SECOND) as window_end,
        COUNT(*) as event_count
    FROM default_catalog.default_database.clickstream_events
    WHERE event_time IS NOT NULL
    GROUP BY 
        TUMBLE(event_time, INTERVAL '10' SECOND),
        user_id
    HAVING COUNT(*) > 5
    """
    
    t_env.execute_sql(fraud_detection_sql)
    print("Fraud detection logic defined (tumbling window > 5 events).") 

    # 6. Create output table in Iceberg
    # ===============================================================
    print("Creating fraud alerts output table...")
    
    create_output_sql = f"""
        CREATE TABLE IF NOT EXISTS fraud_attempts (
            user_id STRING,
            window_start TIMESTAMP(3),
            window_end TIMESTAMP(3),
            event_count BIGINT
        ) WITH (
            'format-version' = '2'
        )
    """
    
    t_env.execute_sql(create_output_sql)
    print("Fraud alerts output table created.")

    # 7. Execute the fraud detection pipeline
    # ===============================================================
    print("Starting fraud detection pipeline...")
    
    # Insert fraud events into the output table using SQL
    insert_sql = f"""
    INSERT INTO fraud_attempts
    SELECT 
        user_id,
        window_start,
        window_end,
        event_count
    FROM fraud_events
    """
    
    print("Submitting job to write to Iceberg table 'demo.fraud_attempts'...")
    result = t_env.execute_sql(insert_sql)
    
    print("Fraud detection pipeline started successfully.")
    print(f"Job submitted with result: {result.get_job_client().get_job_id()}")
    
    # Wait for the job to run (in a real scenario, this would run indefinitely)
    # print("Streaming job is running. Check Flink UI for progress.")
    # result.wait()

if __name__ == "__main__":
    main()