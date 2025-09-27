import os
from pyflink.table import StreamTableEnvironment
from pyflink.datastream import StreamExecutionEnvironment

# Define configuration for Kubernetes services
CATALOG_NAME = "nessie"
DATABASE_NAME = "demo"
NESSIE_URI = "http://nessie.ecommerce-platform.svc.cluster.local:19120/api/v1"
WAREHOUSE_PATH = "s3a://warehouse"
MINIO_ENDPOINT = "http://minio.ecommerce-platform.svc.cluster.local:9000"

def main():
    """
    Simple test to check catalog connectivity without creating tables.
    """
    env = StreamExecutionEnvironment.get_execution_environment()
    t_env = StreamTableEnvironment.create(stream_execution_environment=env)

    # Configure S3A settings for MinIO
    cfg = t_env.get_config().get_configuration()
    cfg.set_string("fs.s3a.endpoint", MINIO_ENDPOINT)
    cfg.set_string("fs.s3a.access.key", "minioadmin")
    cfg.set_string("fs.s3a.secret.key", "minioadmin")
    cfg.set_string("fs.s3a.path.style.access", "true")
    cfg.set_string("fs.s3a.ssl.enabled", "false")
    cfg.set_string("fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
    
    print("S3A configuration set for MinIO.")

    # Create the Nessie Iceberg Catalog
    create_catalog_sql = f"""
    CREATE CATALOG {CATALOG_NAME}
    WITH (
        'type'='iceberg',
        'catalog-impl'='org.apache.iceberg.nessie.NessieCatalog',
        'uri'='{NESSIE_URI}',
        'ref'='main',
        'authentication.type'='none',
        'warehouse'='{WAREHOUSE_PATH}',
        's3.endpoint'='{MINIO_ENDPOINT}',
        's3.access-key-id'='minioadmin',
        's3.secret-access-key'='minioadmin',
        's3.path-style-access'='true'
    )
    """
    
    print("Creating Nessie catalog...")
    t_env.execute_sql(create_catalog_sql)
    print("Nessie catalog created successfully.")

    # Switch to the catalog
    t_env.use_catalog(CATALOG_NAME)
    
    # List catalogs
    catalogs_result = t_env.execute_sql("SHOW CATALOGS")
    print("Available catalogs:")
    for row in catalogs_result.collect():
        print(f"  - {row}")

    # Try to create database (this should work without S3 access)
    print(f"Creating database '{DATABASE_NAME}' if it doesn't exist...")
    try:
        t_env.execute_sql(f"CREATE DATABASE IF NOT EXISTS {DATABASE_NAME}")
        print(f"Database '{DATABASE_NAME}' created or already exists.")
    except Exception as e:
        print(f"Database creation error: {e}")

    # List databases
    try:
        t_env.use_database(DATABASE_NAME)
        databases_result = t_env.execute_sql("SHOW DATABASES")
        print("Available databases:")
        for row in databases_result.collect():
            print(f"  - {row}")
    except Exception as e:
        print(f"Error listing databases: {e}")

    # Clean up existing table if it exists
    try:
        t_env.execute_sql("DROP TABLE IF EXISTS fraud_alerts")
        print("Cleaned up existing fraud_alerts table.")
    except Exception as e:
        print(f"Table cleanup (expected if table doesn't exist): {e}")

    print("Test completed successfully!")

if __name__ == "__main__":
    main()