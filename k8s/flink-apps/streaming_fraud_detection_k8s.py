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
STAGED_CLICKSTREAM_JSON = "s3a://warehouse/data/clickstream.json"
USE_REAL_CLICKSTREAM = True  # attempt real data first

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
        's3.region'='us-east-1'
    )
    """
    
    print("Creating Nessie catalog...")
    t_env.execute_sql(create_catalog_sql)
    print("Nessie catalog created successfully.")

    # 3. Create database if it doesn't exist
    # ===============================================================
    print(f"Creating database '{DATABASE_NAME}' if it doesn't exist...")
    t_env.execute_sql(f"CREATE DATABASE IF NOT EXISTS {CATALOG_NAME}.{DATABASE_NAME}")
    
    # 4. Create source table for clickstream events (real JSON if available, else datagen)
    # ===============================================================
    if USE_REAL_CLICKSTREAM:
        print("Attempting to register real clickstream JSON source...")
        # We'll try to create a filesystem connector table over the JSON file.
        # If it fails, we fallback to datagen.
        real_source_sql = f"""
        CREATE TABLE clickstream_events (
            user_id STRING,
            product_id STRING,
            event_type STRING,
            timestamp_col TIMESTAMP(3),
            WATERMARK FOR timestamp_col AS timestamp_col - INTERVAL '5' SECOND
        ) WITH (
            'connector' = 'filesystem',
            'path' = '{STAGED_CLICKSTREAM_JSON}',
            'format' = 'json'
        )
        """
        try:
            t_env.execute_sql(real_source_sql)
            print("Registered filesystem JSON clickstream source.")
        except Exception as e:
            print(f"Real clickstream source registration failed ({e}); falling back to datagen source.")
            fallback_sql = f"""
            CREATE TABLE clickstream_events (
                user_id BIGINT,
                product_id BIGINT,
                event_type STRING,
                timestamp_col TIMESTAMP(3),
                session_id STRING,
                WATERMARK FOR timestamp_col AS timestamp_col - INTERVAL '5' SECOND
            ) WITH (
                'connector' = 'datagen',
                'rows-per-second' = '10',
                'fields.user_id.min' = '1',
                'fields.user_id.max' = '1000',
                'fields.product_id.min' = '1',
                'fields.product_id.max' = '100',
                'fields.event_type.length' = '10'
            )
            """
            t_env.execute_sql(fallback_sql)
            print("Datagen clickstream source table created.")
    else:
        print("Using datagen source (configured to skip real data).")
        datagen_sql = f"""
        CREATE TABLE clickstream_events (
            user_id BIGINT,
            product_id BIGINT,
            event_type STRING,
            timestamp_col TIMESTAMP(3),
            session_id STRING,
            WATERMARK FOR timestamp_col AS timestamp_col - INTERVAL '5' SECOND
        ) WITH (
            'connector' = 'datagen',
            'rows-per-second' = '10',
            'fields.user_id.min' = '1',
            'fields.user_id.max' = '1000',
            'fields.product_id.min' = '1',
            'fields.product_id.max' = '100',
            'fields.event_type.length' = '10'
        )
        """
        t_env.execute_sql(datagen_sql)
        print("Datagen clickstream source table created.")

    # 5. Create fraud detection logic
    # ===============================================================
    print("Setting up fraud detection logic...")
    
    # Create a view for fraud detection
    fraud_detection_sql = f"""
    CREATE TEMPORARY VIEW fraud_events AS
    SELECT 
        user_id,
        event_type,
        COUNT(*) as event_count,
        TUMBLE_START(timestamp_col, INTERVAL '1' MINUTE) as window_start,
        TUMBLE_END(timestamp_col, INTERVAL '1' MINUTE) as window_end
    FROM clickstream_events
    GROUP BY 
        TUMBLE(timestamp_col, INTERVAL '1' MINUTE),
        user_id,
        event_type
    HAVING COUNT(*) > 50
    """
    
    t_env.execute_sql(fraud_detection_sql)

    # 6. Create output table in Iceberg
    # ===============================================================
    print("Creating fraud alerts output table...")
    
    create_output_sql = f"""
    CREATE TABLE IF NOT EXISTS {CATALOG_NAME}.{DATABASE_NAME}.fraud_alerts (
        user_id BIGINT,
        event_type STRING,
        event_count BIGINT NOT NULL,
        window_start TIMESTAMP(3) NOT NULL,
        window_end TIMESTAMP(3) NOT NULL,
        alert_timestamp TIMESTAMP_LTZ(3) NOT NULL
    )
    """
    
    t_env.execute_sql(create_output_sql)
    print("Fraud alerts output table created.")

    # 7. Execute the fraud detection pipeline
    # ===============================================================
    print("Starting fraud detection pipeline...")
    
    # Insert fraud events into the output table
    insert_sql = f"""
    INSERT INTO {CATALOG_NAME}.{DATABASE_NAME}.fraud_alerts
    SELECT 
        CAST(user_id AS BIGINT) as user_id,
        event_type,
        event_count,
        window_start,
        window_end,
        CURRENT_TIMESTAMP as alert_timestamp
    FROM fraud_events
    """
    
    # Execute the streaming job
    result = t_env.execute_sql(insert_sql)
    print("Fraud detection pipeline started successfully.")
    
    # Wait for the job to run (in a real scenario, this would run indefinitely)
    print("Streaming job is running. Check Flink UI for progress.")
    result.wait()

if __name__ == "__main__":
    main()