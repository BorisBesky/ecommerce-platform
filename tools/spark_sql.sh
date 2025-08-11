#!/bin/bash
set -e

# Parse command line arguments
EXECUTE_SQL=""
while [[ $# -gt 0 ]]; do
  case $1 in
    -e)
      EXECUTE_SQL="$2"
      shift 2
      ;;
    *)
      echo "Unknown option $1"
      echo "Usage: $0 [-e 'SQL statement']"
      exit 1
      ;;
  esac
done

cd ../docker

# Check if Spark master is already running
if ! docker-compose ps spark-master | grep -q "Up"; then
  echo "Starting Spark master..."
  docker-compose up -d spark-master
  
  # Wait for Spark master to be ready
  echo "Waiting for Spark master to be ready..."
  while ! docker-compose exec spark-master spark-sql --version &>/dev/null; do
    sleep 1
  done
  echo "Spark master is ready!"
else
  echo "Spark master is already running"
fi

# Execute the spark-sql command
if [[ -n "$EXECUTE_SQL" ]]; then
  # Execute with SQL statement
  docker-compose exec spark-master spark-sql \
    --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.3,org.projectnessie.nessie-integrations:nessie-spark-extensions-3.5_2.12:0.77.1,org.apache.hadoop:hadoop-aws:3.3.4 \
    --conf spark.sql.catalog.nessie.warehouse="s3a://warehouse" \
    --conf spark.sql.catalog.nessie=org.apache.iceberg.spark.SparkCatalog \
    --conf spark.sql.catalog.nessie.catalog-impl=org.apache.iceberg.nessie.NessieCatalog \
    --conf spark.sql.catalog.nessie.uri=http://nessie:19120/api/v1 \
    --conf spark.sql.catalog.nessie.ref=main \
    --conf spark.sql.catalog.nessie.authentication.type=NONE \
    --conf spark.sql.extensions="org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,org.projectnessie.spark.extensions.NessieSparkSessionExtensions" \
    --conf spark.hadoop.fs.s3a.endpoint=http://minio:9000 \
    --conf spark.hadoop.fs.s3a.access.key=minioadmin \
    --conf spark.hadoop.fs.s3a.secret.key=minioadmin \
    --conf spark.hadoop.fs.s3a.path.style.access=true \
    --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
    -e "$EXECUTE_SQL"
else
  # Interactive mode
  docker-compose exec spark-master spark-sql \
    --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.3,org.projectnessie.nessie-integrations:nessie-spark-extensions-3.5_2.12:0.77.1,org.apache.hadoop:hadoop-aws:3.3.4 \
    --conf spark.sql.catalog.nessie.warehouse="s3a://warehouse" \
    --conf spark.sql.catalog.nessie=org.apache.iceberg.spark.SparkCatalog \
    --conf spark.sql.catalog.nessie.catalog-impl=org.apache.iceberg.nessie.NessieCatalog \
    --conf spark.sql.catalog.nessie.uri=http://nessie:19120/api/v1 \
    --conf spark.sql.catalog.nessie.ref=main \
    --conf spark.sql.catalog.nessie.authentication.type=NONE \
    --conf spark.sql.extensions="org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,org.projectnessie.spark.extensions.NessieSparkSessionExtensions" \
    --conf spark.hadoop.fs.s3a.endpoint=http://minio:9000 \
    --conf spark.hadoop.fs.s3a.access.key=minioadmin \
    --conf spark.hadoop.fs.s3a.secret.key=minioadmin \
    --conf spark.hadoop.fs.s3a.path.style.access=true \
    --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem
fi