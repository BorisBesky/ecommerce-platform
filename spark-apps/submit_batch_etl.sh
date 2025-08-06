#!/bin/bash
cd ../docker
# Ensure the Spark master is running
docker-compose up -d spark-master
# Wait for Spark master to be ready
sleep 5
# Submit the Spark job to run the ETL process
# Using Nessie and Iceberg for data management
# Ensure the necessary packages are included in the Spark submit command
# The job will read from the mounted data directory and write to the Iceberg table in S3
# The S3 bucket is configured to use MinIO as the storage backend
# The Spark job will use Nessie for version control of the Iceberg table
# The job will run in the Spark master container
# The Spark job will read user and product data from the mounted /data directory
# and write the processed data to an Iceberg table in the S3 bucket configured in MinIO
docker-compose exec spark-master spark-submit \
  --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.3,org.projectnessie.nessie-integrations:nessie-spark-extensions-3.5_2.12:0.77.1,org.apache.hadoop:hadoop-aws:3.3.4 \
  --conf spark.sql.catalog.nessie=org.apache.iceberg.spark.SparkCatalog \
  --conf spark.sql.catalog.nessie.uri=http://nessie:19120/api/v1 \
  --conf spark.sql.catalog.nessie.ref=main \
  --conf spark.sql.catalog.nessie.authentication.type=NONE \
  --conf spark.sql.catalog.nessie.catalog-impl=org.apache.iceberg.nessie.NessieCatalog \
  --conf spark.sql.catalog.nessie.warehouse=s3a://warehouse \
  --conf spark.sql.extensions="org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,org.projectnessie.spark.extensions.NessieSparkSessionExtensions" \
  --conf spark.hadoop.fs.s3a.endpoint=http://minio:9000 \
  --conf spark.hadoop.fs.s3a.access.key=minioadmin \
  --conf spark.hadoop.fs.s3a.secret.key=minioadmin \
  --conf spark.hadoop.fs.s3a.path.style.access=true \
  --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
  /apps/batch_etl.py