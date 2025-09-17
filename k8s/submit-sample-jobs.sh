#!/bin/bash

# Sample Jobs Submission Script
# This script submits sample jobs to test each component of the platform

set -e

echo "🚀 E-commerce Platform - Sample Jobs Submission"
echo "==============================================="

NAMESPACE="ecommerce-platform"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is not installed or not in PATH"
    exit 1
fi

# Function to wait for job completion
wait_for_job() {
    local job_type=$1
    local job_name=$2
    local timeout=${3:-300}
    
    echo "   ⏳ Waiting for $job_type job '$job_name' to complete..."
    
    case $job_type in
        "spark")
            # For Spark, we'll just wait a bit since it's submitted directly
            sleep 30
            ;;
        "flink")
            # For Flink, check if the job is running
            sleep 30
            ;;
        "ray")
            kubectl wait --for=condition=JobDeploymentStatus rayjob/$job_name -n $NAMESPACE --timeout=${timeout}s || true
            ;;
    esac
}

echo "📋 This script will submit sample jobs to test the platform components:"
echo "   1. Spark ETL Job (batch processing)"
echo "   2. Flink Streaming Job (real-time fraud detection)"
echo "   3. Ray Training Job (recommendation model)"
echo ""

# Step 1: Prepare sample data
echo "📁 Step 1: Preparing sample data..."
cat > /tmp/sample_users.csv << 'EOF'
user_id,name,email,signup_date,is_fraud
1,John Doe,john@example.com,2023-01-15,false
2,Jane Smith,jane@example.com,2023-02-20,false
3,Bob Wilson,bob@example.com,2023-03-10,false
4,Alice Brown,alice@example.com,2023-04-05,true
5,Charlie Davis,charlie@example.com,2023-05-12,false
EOF

cat > /tmp/sample_products.csv << 'EOF'
product_id,name,category,price
1,Laptop,Electronics,999.99
2,Smartphone,Electronics,599.99
3,Headphones,Electronics,199.99
4,Book,Books,29.99
5,Shoes,Clothing,89.99
EOF

echo "   ✅ Sample data files created"

# Step 2: Upload data to a pod for processing
echo ""
echo "📤 Step 2: Uploading sample data..."

# Create a data uploader pod
kubectl run data-uploader -n $NAMESPACE --image=busybox --rm -i --restart=Never -- sh -c "
mkdir -p /data
cat > /data/users.csv << 'EOF'
user_id,name,email,signup_date,is_fraud
1,John Doe,john@example.com,2023-01-15,false
2,Jane Smith,jane@example.com,2023-02-20,false
3,Bob Wilson,bob@example.com,2023-03-10,false
4,Alice Brown,alice@example.com,2023-04-05,true
5,Charlie Davis,charlie@example.com,2023-05-12,false
EOF

cat > /data/products.csv << 'EOF'
product_id,name,category,price
1,Laptop,Electronics,999.99
2,Smartphone,Electronics,599.99
3,Headphones,Electronics,199.99
4,Book,Books,29.99
5,Shoes,Clothing,89.99
EOF

echo 'Sample data prepared'
"

echo "   ✅ Sample data uploaded"

# Step 3: Submit Spark ETL Job
echo ""
echo "⚡ Step 3: Submitting Spark ETL Job..."

# Create a Spark job submission pod
kubectl run spark-job-submitter -n $NAMESPACE --image=bitnami/spark:3.5.0 --rm -i --restart=Never -- \
    spark-submit \
    --master spark://spark-master:7077 \
    --deploy-mode client \
    --conf spark.sql.catalog.nessie=org.apache.iceberg.spark.SparkCatalog \
    --conf spark.sql.catalog.nessie.uri=http://nessie:19120/api/v1 \
    --conf spark.sql.catalog.nessie.ref=main \
    --conf spark.sql.catalog.nessie.authentication.type=NONE \
    --conf spark.sql.catalog.nessie.catalog-impl=org.apache.iceberg.nessie.NessieCatalog \
    --conf spark.sql.catalog.nessie.warehouse=s3a://warehouse \
    --conf spark.sql.extensions="org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions" \
    --conf spark.hadoop.fs.s3a.endpoint=http://minio:9000 \
    --conf spark.hadoop.fs.s3a.access.key=minioadmin \
    --conf spark.hadoop.fs.s3a.secret.key=minioadmin \
    --conf spark.hadoop.fs.s3a.path.style.access=true \
    --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
    /apps/batch_etl_k8s.py

echo "   ✅ Spark ETL job submitted"

# Step 4: Submit Flink Streaming Job
echo ""
echo "🌊 Step 4: Submitting Flink Streaming Job..."

# Get the Flink JobManager pod name
FLINK_JOBMANAGER_POD=$(kubectl get pods -l app=flink,component=jobmanager -n $NAMESPACE -o jsonpath='{.items[0].metadata.name}')

if [[ -n "$FLINK_JOBMANAGER_POD" ]]; then
    kubectl exec $FLINK_JOBMANAGER_POD -n $NAMESPACE -- \
        flink run --detached -py /apps/streaming_fraud_detection_k8s.py
    echo "   ✅ Flink streaming job submitted"
else
    echo "   ❌ Flink JobManager pod not found"
fi

# Step 5: Submit Ray Training Job
echo ""
echo "🧠 Step 5: Submitting Ray Training Job..."

# Apply the Ray job
kubectl apply -f "${SCRIPT_DIR}/ray.yaml"

wait_for_job "ray" "rayjob-recommendations-training" 600

echo "   ✅ Ray training job submitted"

echo ""
echo "📊 Step 6: Checking job statuses..."

echo ""
echo "Spark Master UI: kubectl port-forward svc/spark-master 8080:8080 -n $NAMESPACE"
echo "Flink JobManager UI: kubectl port-forward svc/flink-jobmanager 8081:8081 -n $NAMESPACE"
echo "Ray Job Status: kubectl get rayjob rayjob-recommendations-training -n $NAMESPACE"

echo ""
echo "✅ Sample jobs submitted successfully!"
echo ""
echo "📋 To monitor jobs:"
echo "   - Spark: Check the Spark Master UI"
echo "   - Flink: Check the Flink JobManager UI"
echo "   - Ray: kubectl describe rayjob rayjob-recommendations-training -n $NAMESPACE"
echo ""
echo "📁 To check results:"
echo "   - Access MinIO Console: kubectl port-forward svc/minio 9001:9001 -n $NAMESPACE"
echo "   - Check the 'warehouse' bucket for processed data"