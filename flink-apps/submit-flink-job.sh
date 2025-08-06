#!/bin/bash
set -e
set -x

cd ../docker
# Submit the Flink job to run the streaming fraud detection process
# Using Iceberg for data management (temporarily without Nessie)
# Ensure the necessary packages are included in the Flink submit command
# The job will read from the mounted data directory and write to the Iceberg table in S3
# The S3 bucket is configured to use MinIO as the storage backend
# The job will run in the Flink job manager container

docker-compose exec flink-jobmanager flink run \
  --python /apps/streaming-fraud-detection.py \
  --pyRequirements /apps/requirements.txt \
  -d