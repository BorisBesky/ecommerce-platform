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

# Step 2: Stage sample data in MinIO (warehouse bucket)
echo ""
echo "📤 Step 2: Staging sample data to MinIO..."

# We'll create a short-lived pod with the MinIO client (mc) to upload the local heredoc data.
# Data layout target:
#   s3a://warehouse/data/users.csv
#   s3a://warehouse/data/products.csv

MINIO_ALIAS="local"
MINIO_ENDPOINT_INTERNAL="http://minio:9000"   # in-cluster service
MINIO_ACCESS_KEY="minioadmin"
MINIO_SECRET_KEY="minioadmin"
WAREHOUSE_BUCKET="warehouse"

# Create a Kubernetes ConfigMap on-the-fly for the two CSV files (simpler than inline cat inside pod) OR pipe directly.
# Simpler approach: pipe via stdin into pod and upload with mc.

kubectl run data-uploader -n $NAMESPACE --image=minio/mc:latest --restart=Never --rm -i -- bash -lc "
set -e
echo '🔧 Configuring mc client...'
mc alias set $MINIO_ALIAS $MINIO_ENDPOINT_INTERNAL $MINIO_ACCESS_KEY $MINIO_SECRET_KEY >/dev/null

echo '🪣 Ensuring bucket exists...'
if ! mc ls $MINIO_ALIAS/$WAREHOUSE_BUCKET >/dev/null 2>&1; then
    mc mb $MINIO_ALIAS/$WAREHOUSE_BUCKET || true
fi

echo '⬆️  Uploading users.csv...'
cat > /tmp/users.csv <<'USERS'
user_id,name,email,signup_date,is_fraud
1,John Doe,john@example.com,2023-01-15,false
2,Jane Smith,jane@example.com,2023-02-20,false
3,Bob Wilson,bob@example.com,2023-03-10,false
4,Alice Brown,alice@example.com,2023-04-05,true
5,Charlie Davis,charlie@example.com,2023-05-12,false
USERS
mc cp /tmp/users.csv $MINIO_ALIAS/$WAREHOUSE_BUCKET/data/users.csv

echo '⬆️  Uploading products.csv...'
cat > /tmp/products.csv <<'PRODS'
product_id,name,category,price
1,Laptop,Electronics,999.99
2,Smartphone,Electronics,599.99
3,Headphones,Electronics,199.99
4,Book,Books,29.99
5,Shoes,Clothing,89.99
PRODS
mc cp /tmp/products.csv $MINIO_ALIAS/$WAREHOUSE_BUCKET/data/products.csv

echo '📄 Listing uploaded objects:'
mc ls $MINIO_ALIAS/$WAREHOUSE_BUCKET/data/
echo '✅ Data staged to MinIO.'
"

echo "   ✅ Sample data staged in MinIO (s3a://warehouse/data/)"

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

# Step 5: Submit Ray Training Job (prefer existing cluster)
echo ""
echo "🧠 Step 5: Submitting Ray Training Job..."

USE_EXISTING_RAY=${USE_EXISTING_RAY:-true}

if [[ "$USE_EXISTING_RAY" == "true" ]]; then
    RAY_HEAD_POD=$(kubectl get pods -n $NAMESPACE -l app=ray,component=head -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
    if [[ -n "$RAY_HEAD_POD" ]]; then
        echo "   🔍 Detected existing Ray head pod: $RAY_HEAD_POD"
        echo "   🚀 Submitting training script to existing cluster (exec into head pod)"
        # Execute the training script inside the head pod. Assumes /apps mount with script exists.
        if kubectl exec -n $NAMESPACE "$RAY_HEAD_POD" -- test -f /apps/train_recommendation_model_k8s.py; then
            kubectl exec -n $NAMESPACE "$RAY_HEAD_POD" -- bash -lc "python /apps/train_recommendation_model_k8s.py"
            echo "   ✅ Ray training script executed on existing cluster"
        else
            echo "   ⚠️  Training script not found at /apps/train_recommendation_model_k8s.py in existing cluster. Falling back to RayJob submission."
            RAY_HEAD_POD="" # force fallback
        fi
    else
        echo "   ℹ️  No existing Ray head pod detected. Will submit RayJob manifest."
    fi
fi

if [[ -z "$RAY_HEAD_POD" ]]; then
    echo "   📄 Applying RayJob manifest: ${SCRIPT_DIR}/ray.yaml"
    kubectl apply -f "${SCRIPT_DIR}/ray.yaml"
    wait_for_job "ray" "rayjob-recommendations-training" 600
    echo "   ✅ Ray training RayJob submitted (new or reused job controller)"
fi

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