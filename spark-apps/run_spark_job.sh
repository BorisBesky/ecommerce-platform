#!/bin/bash

/opt/spark/bin/spark-submit \
  --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.3,org.projectnessie.nessie-integrations:nessie-spark-extensions-3.5_2.12:0.77.1,org.apache.hadoop:hadoop-aws:3.3.4 \
  --conf spark.sql.catalog.nessie.warehouse="s3a://warehouse" \
  --master spark://spark-master:7077 \
  /apps/batch_etl.py 