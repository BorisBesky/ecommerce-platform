from pyspark.sql import SparkSession
from pyspark.sql.functions import col

# Define configuration settings for Kubernetes deployment
# These settings connect Spark to our Kubernetes services: Nessie for the catalog and MinIO for storage.
CATALOG_NAME = "nessie"
NESSIE_URI = "http://nessie.ecommerce-platform.svc.cluster.local:19120/api/v1"
WAREHOUSE_PATH = "s3a://warehouse" # 'warehouse' is the bucket name in MinIO
MINIO_ENDPOINT = "http://minio.ecommerce-platform.svc.cluster.local:9000"

# Input data paths within the container
USERS_DATA_PATH = "/data/users.csv"
PRODUCTS_DATA_PATH = "/data/products.csv"

def main():
    """
    Main ETL job function for Kubernetes deployment.
    Initializes Spark, reads CSV data, and writes it to Iceberg tables.
    """
    spark = None
    try:
        # 1. Initialize Spark Session with Iceberg and S3 configurations
        # =================================================================
        print("Initializing Spark session for Kubernetes deployment...")
        
        builder = (
            SparkSession.builder
            .appName("EcommercePlatform-BatchETL-K8s")
            .config(f"spark.sql.catalog.{CATALOG_NAME}", "org.apache.iceberg.spark.SparkCatalog")
            .config(f"spark.sql.catalog.{CATALOG_NAME}.catalog-impl", "org.apache.iceberg.nessie.NessieCatalog")
            .config(f"spark.sql.catalog.{CATALOG_NAME}.uri", NESSIE_URI)
            .config(f"spark.sql.catalog.{CATALOG_NAME}.ref", "main")
            .config(f"spark.sql.catalog.{CATALOG_NAME}.authentication.type", "NONE")
            .config(f"spark.sql.catalog.{CATALOG_NAME}.warehouse", WAREHOUSE_PATH)
            .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,org.projectnessie.spark.extensions.NessieSparkSessionExtensions")
            # S3/MinIO configuration for Kubernetes
            .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT)
            .config("spark.hadoop.fs.s3a.access.key", "minioadmin")
            .config("spark.hadoop.fs.s3a.secret.key", "minioadmin")
            .config("spark.hadoop.fs.s3a.path.style.access", "true")
            .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
            # Additional configurations for better Kubernetes compatibility
            .config("spark.sql.adaptive.enabled", "true")
            .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        )

        spark = builder.getOrCreate()
        print("Spark session initialized successfully for Kubernetes.")

        # 2. Create the 'demo' namespace (database) if it doesn't exist
        # =================================================================
        print("Creating database 'demo' if it does not exist...")
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {CATALOG_NAME}.demo")
        print("Database 'demo' is ready.")

        # 3. Process and Write the Users Table
        # =================================================================
        print(f"Reading user data from {USERS_DATA_PATH}...")
        # For production, defining a schema explicitly is better than inferSchema.
        users_df = spark.read.csv(USERS_DATA_PATH, header=True, inferSchema=True)
        
        # Simple transformation: Ensure signup_date is a date type
        users_df = users_df.withColumn("signup_date", col("signup_date").cast("date"))
        
        print(f"Writing {users_df.count()} users to Iceberg table '{CATALOG_NAME}.demo.users'...")
        users_df.writeTo(f"{CATALOG_NAME}.demo.users").createOrReplace()
        print("Users table created successfully.")

        # 4. Process and Write the Products Table
        # =================================================================
        print(f"Reading product data from {PRODUCTS_DATA_PATH}...")
        products_df = spark.read.csv(PRODUCTS_DATA_PATH, header=True, inferSchema=True)

        # Simple transformation: Ensure price is a double type
        products_df = products_df.withColumn("price", col("price").cast("double"))

        print(f"Writing {products_df.count()} products to Iceberg table '{CATALOG_NAME}.demo.products'...")
        products_df.writeTo(f"{CATALOG_NAME}.demo.products").createOrReplace()
        print("Products table created successfully.")

        print("\\nETL Job Finished Successfully!")

    except Exception as e:
        print(f"An error occurred: {e}")
        raise
    finally:
        if spark:
            print("Stopping Spark session.")
            spark.stop()

if __name__ == '__main__':
    main()