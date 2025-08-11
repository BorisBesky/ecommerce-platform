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

# Define configuration for Docker services
CATALOG_NAME = "nessie"
DATABASE_NAME = "demo"
NESSIE_URI = "http://nessie:19120/api/v1"
WAREHOUSE_PATH = "s3a://warehouse"
MINIO_ENDPOINT = "http://minio:9000"

# Path inside the Flink container where the clickstream data will be mounted
# Flink will monitor this directory for new files.
SOURCE_DATA_PATH = "/data"

def main():
    """
    Main Flink streaming job for real-time fraud detection.
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

    # Add the necessary JAR files to the Flink cluster's classpath.
    # This is crucial for PyFlink to use Java-based connectors.
    # These paths correspond to where we will mount the JARs in the container.
    t_env.get_config().set(
        "pipeline.jars",
    "file:///flink-jars/iceberg-flink-runtime-1.4.3.jar;"
    "file:///flink-jars/hadoop-common-3.3.4.jar;"
    "file:///flink-jars/hadoop-aws-3.3.4.jar"
    )

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
    t_env.execute_sql(create_catalog_sql)
    print("Iceberg catalog 'nessie' created and registered.")

    # Set the current catalog to Nessie for the session
    t_env.use_catalog(CATALOG_NAME)
    t_env.use_database(DATABASE_NAME)

    # 3. Define the Source Table (Clickstream)
    # ===============================================================
    # This tells Flink to monitor a directory for JSON files.
    # It will treat each line in a file as a separate JSON object.
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
    print("Source table defined to read from filesystem.")

    # 4. Define the Fraud Detection Logic
    # ===============================================================
    # This is the core of our streaming job.
    # - We group by a 10-second tumbling window and user_id.
    # - We count the number of events in each group.
    # - We filter for groups where the count is > 5.
    fraud_attempts = (
        source_table.window(
            Tumble.over(lit(10).seconds).on(col("event_time")).alias("w")
        )
        .group_by(col("w"), col("user_id"))
        .select(
            col("user_id"),
            col("w").start.alias("window_start"),
            col("w").end.alias("window_end"),
            col("user_id").count.alias("event_count"),
        )
        .where(col("event_count") > 5)
    )
    print("Fraud detection logic defined (tumbling window > 5 events).")
    
    # For debugging: print the fraudulent attempts to the console
    # fraud_attempts.execute().print()

    # 5. Create the Sink Table (Iceberg) and Submit the Job
    # ===============================================================
    # First, create the fraud_attempts table if it doesn't exist
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
    print("Created Iceberg table 'demo.fraud_attempts'.")
    
    # Now insert the results from our query
    print("Submitting job to write to Iceberg table 'demo.fraud_attempts'...")
    fraud_attempts.execute_insert("fraud_attempts").wait()
    
    print("Job submitted successfully!")


if __name__ == "__main__":
    main()
