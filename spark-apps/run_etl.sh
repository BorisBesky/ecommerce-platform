#!/bin/bash

# Set Ivy repository path to a writable directory
export IVY_LOCAL_REPO=/tmp/.ivy2

# Create the directory if it doesn't exist
mkdir -p $IVY_LOCAL_REPO

# Run the ETL job
spark-submit \
  --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.3,org.projectnessie.nessie-integrations:nessie-spark-extensions-3.5_2.12:0.77.1,org.apache.hadoop:hadoop-aws:3.3.4 \
  --conf spark.sql.catalog.nessie.warehouse="s3a://warehouse" \
  --conf spark.jars.ivy=$IVY_LOCAL_REPO \
  --conf spark.hadoop.hadoop.security.authentication=simple \
  --conf spark.hadoop.hadoop.security.authorization=false \
  --master spark://spark-master:7077 \
  /apps/batch_etl.py 