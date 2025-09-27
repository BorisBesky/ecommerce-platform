#!/bin/bash
set -e

# Parse command line arguments
EXECUTE_SQL=""
NAMESPACE="ecommerce-platform"
while [[ $# -gt 0 ]]; do
  case $1 in
    -e)
      EXECUTE_SQL="$2"
      shift 2
      ;;
    -n|--namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    *)
      echo "Unknown option $1"
      echo "Usage: $0 [-e 'SQL statement'] [-n namespace]"
      exit 1
      ;;
  esac
done

# Check if Spark master is running in Kubernetes
echo "Checking Spark master status in namespace: $NAMESPACE"
SPARK_MASTER_POD=$(kubectl get pods -l app=spark,component=master -n $NAMESPACE -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [[ -z "$SPARK_MASTER_POD" ]]; then
  echo "Error: Spark master pod not found in namespace $NAMESPACE"
  echo "Please ensure Spark is deployed to Kubernetes first."
  echo "You can deploy it with: kubectl apply -f k8s/spark.yaml"
  exit 1
fi

# Check if the pod is ready
POD_STATUS=$(kubectl get pod $SPARK_MASTER_POD -n $NAMESPACE -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
if [[ "$POD_STATUS" != "Running" ]]; then
  echo "Error: Spark master pod is not running. Status: $POD_STATUS"
  echo "Please check the pod status with: kubectl get pods -n $NAMESPACE"
  exit 1
fi

echo "Spark master pod found: $SPARK_MASTER_POD"

# Common Spark SQL configuration for Iceberg and Nessie
SPARK_CONF="--packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.3,org.projectnessie.nessie-integrations:nessie-spark-extensions-3.5_2.12:0.77.1,org.apache.hadoop:hadoop-aws:3.3.4 \
--conf spark.sql.catalog.nessie.warehouse=s3a://warehouse \
--conf spark.sql.catalog.nessie=org.apache.iceberg.spark.SparkCatalog \
--conf spark.sql.catalog.nessie.catalog-impl=org.apache.iceberg.nessie.NessieCatalog \
--conf spark.sql.catalog.nessie.uri=http://nessie.ecommerce-platform.svc.cluster.local:19120/api/v1 \
--conf spark.sql.catalog.nessie.ref=main \
--conf spark.sql.catalog.nessie.authentication.type=NONE \
--conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,org.projectnessie.spark.extensions.NessieSparkSessionExtensions \
--conf spark.hadoop.fs.s3a.endpoint=http://minio.ecommerce-platform.svc.cluster.local:9000 \
--conf spark.hadoop.fs.s3a.access.key=minioadmin \
--conf spark.hadoop.fs.s3a.secret.key=minioadmin \
--conf spark.hadoop.fs.s3a.path.style.access=true \
--conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem"

# Execute the spark-sql command in the Kubernetes pod
if [[ -n "$EXECUTE_SQL" ]]; then
  # Execute with SQL statement
  echo "Executing SQL statement in Spark master pod..."
  kubectl exec -n $NAMESPACE $SPARK_MASTER_POD -- spark-sql $SPARK_CONF -e "$EXECUTE_SQL"
else
  # Interactive mode
  echo "Starting interactive Spark SQL session..."
  echo "Note: Use 'USE nessie;' to switch to the Nessie catalog"
  echo "Available catalogs: spark_catalog, nessie"
  echo "Press Ctrl+C to exit"
  kubectl exec -it -n $NAMESPACE $SPARK_MASTER_POD -- spark-sql $SPARK_CONF
fi