#!/bin/bash

# Complete MinIO-integrated Ray Recommendations Training Deployment
# This script handles data upload, deployment, and monitoring for the MinIO-integrated training job

set -e

echo "🚀 Complete Ray Recommendations Training with MinIO Integration"
echo "=============================================================="

# Configuration
MINIO_ENDPOINT="http://localhost:9000"
MINIO_CONSOLE="http://localhost:9001"
YAML_FILE="ray-job.recommendations-training.yaml"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is not installed or not in PATH"
    exit 1
fi

# Check if docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ docker is not installed or not in PATH"
    exit 1
fi

# Check if python3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 is not installed or not in PATH"
    exit 1
fi

echo "✅ Prerequisites check passed"

# Step 1: Start MinIO if not running
echo ""
echo "📦 Step 1: Ensuring MinIO is running..."
if ! docker ps | grep -q minio; then
    echo "   Starting MinIO container..."
    cd ../docker && docker-compose up -d minio
    echo "   Waiting for MinIO to be ready..."
    sleep 10
else
    echo "   ✅ MinIO is already running"
fi

# Step 2: Upload data to MinIO
echo ""
echo "📤 Step 2: Uploading clickstream data to MinIO..."
UPLOAD_SCRIPT="../tools/upload-data-to-minio.py"
if [ -f "$UPLOAD_SCRIPT" ]; then
    python3 "$UPLOAD_SCRIPT"
else
    echo "❌ $UPLOAD_SCRIPT not found"
    exit 1
fi

# Step 3: Check KubeRay operator
echo ""
echo "🔍 Step 3: Checking KubeRay operator..."
if ! kubectl get crd rayjobs.ray.io &> /dev/null; then
    echo "❌ KubeRay operator is not installed. Please install it first:"
    echo "   helm repo add kuberay https://ray-project.github.io/kuberay-helm/"
    echo "   helm install kuberay-operator kuberay/kuberay-operator --version 1.0.0"
    exit 1
else
    echo "   ✅ KubeRay operator is installed"
fi

# Step 4: Clean up existing job
echo ""
echo "🧹 Step 4: Cleaning up any existing training job..."
if kubectl get rayjob rayjob-recommendations-training &> /dev/null; then
    echo "   Deleting existing job..."
    kubectl delete rayjob rayjob-recommendations-training
    echo "   Waiting for cleanup..."
    sleep 10
else
    echo "   ✅ No existing job to clean up"
fi

# Step 5: Update ConfigMap with latest script
echo ""
echo "📦 Step 5: Setting up training script ConfigMap..."
if kubectl get configmap ray-training-script &> /dev/null; then
    echo "   Updating existing ConfigMap..."
    kubectl delete configmap ray-training-script
fi

TRAINING_SCRIPT="../ray-apps/train_recommendation_model_minio.py"
if [ ! -f "$TRAINING_SCRIPT" ]; then
    echo "❌ Training script not found: $TRAINING_SCRIPT"
    exit 1
fi

kubectl create configmap ray-training-script --from-file="$TRAINING_SCRIPT"
echo "   ✅ ConfigMap created successfully"

# Step 6: Deploy the training job
echo ""
echo "🚀 Step 6: Deploying recommendation training job..."
if [ ! -f "$YAML_FILE" ]; then
    echo "❌ RayJob YAML file not found: $YAML_FILE"
    exit 1
fi

kubectl apply -f "$YAML_FILE"

# Step 7: Monitor job execution
echo ""
echo "⏳ Step 7: Monitoring job execution..."
echo "   Waiting for job to start..."
kubectl wait --for=condition=JobDeploymentStatus --timeout=300s rayjob/rayjob-recommendations-training

# Monitor job progress
echo "   Monitoring job progress..."
timeout 300s bash -c '
    while true; do
        STATUS=$(kubectl get rayjob rayjob-recommendations-training -o jsonpath="{.status.jobStatus}" 2>/dev/null || echo "UNKNOWN")
        case $STATUS in
            "SUCCEEDED")
                echo "✅ Job completed successfully!"
                break
                ;;
            "FAILED")
                echo "❌ Job failed!"
                exit 1
                ;;
            "RUNNING")
                echo "   📊 Job is running..."
                sleep 10
                ;;
            "PENDING")
                echo "   ⏳ Job is pending..."
                sleep 5
                ;;
            *)
                echo "   📍 Job status: $STATUS"
                sleep 5
                ;;
        esac
    done
' || echo "⏰ Timeout reached, check job status manually"

# Step 8: Show results
echo ""
echo "📊 Step 8: Training Results"
echo "=========================="

# Get final job status
FINAL_STATUS=$(kubectl get rayjob rayjob-recommendations-training -o jsonpath="{.status.jobStatus}" 2>/dev/null || echo "UNKNOWN")
echo "   Job Status: $FINAL_STATUS"

if [ "$FINAL_STATUS" = "SUCCEEDED" ]; then
    # Get job runner pod name
    JOB_POD=$(kubectl get pods --no-headers 2>/dev/null | grep rayjob-recommendations-training | grep -v head | grep -v worker | awk '{print $1}' | head -1)
    
    if [ -n "$JOB_POD" ]; then
        echo ""
        echo "📝 Training Summary (last 15 lines):"
        echo "-----------------------------------"
        kubectl logs "$JOB_POD" 2>/dev/null | grep -E "(Training|Model|✅|🎯|📊)" | tail -15 || echo "Logs not available"
    fi
    
    # Verify model in MinIO
    echo ""
    echo "🔍 Verifying model in MinIO..."
    python3 -c "
import boto3
from botocore.config import Config

try:
    s3_client = boto3.client(
        's3',
        endpoint_url='$MINIO_ENDPOINT',
        aws_access_key_id='minioadmin',
        aws_secret_access_key='minioadmin',
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )
    
    response = s3_client.head_object(Bucket='warehouse', Key='models/recommendation_model.pkl')
    size_mb = response['ContentLength'] / (1024 * 1024)
    print(f'✅ Model found in MinIO: {size_mb:.2f} MB')
    print('📍 Location: s3://warehouse/models/recommendation_model.pkl')
except Exception as e:
    print(f'❌ Model verification failed: {e}')
"
else
    echo "❌ Job did not complete successfully"
fi

echo ""
echo "🎉 Deployment Complete!"
echo "======================"
echo ""
echo "📋 Useful Information:"
echo "   MinIO Console: $MINIO_CONSOLE (minioadmin/minioadmin)"
echo "   MinIO API: $MINIO_ENDPOINT"
echo "   Data Location: s3://warehouse/data/clickstream/"
echo "   Model Location: s3://warehouse/models/recommendation_model.pkl"
echo ""
echo "📋 Useful Commands:"
echo "   Check job status: kubectl get rayjob rayjob-recommendations-training"
echo "   View job details: kubectl describe rayjob rayjob-recommendations-training"
echo "   View all pods: kubectl get pods | grep recommendation"
echo "   Delete job: kubectl delete rayjob rayjob-recommendations-training"
echo ""
echo "🎯 Next Steps:"
echo "   1. Access MinIO console to verify data and model"
echo "   2. Use the trained model in your recommendation service"
echo "   3. Set up periodic retraining with CronJob"
