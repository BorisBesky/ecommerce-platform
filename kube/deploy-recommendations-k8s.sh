#!/bin/bash

# Enhanced deployment script for Ray Recommendations Training Job
# This script handles the ConfigMap approach for Kubernetes deployment

set -e

echo "🚀 Deploying Ray Recommendations Training Job (Kubernetes version)..."

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is not installed or not in PATH"
    exit 1
fi

# Check if the YAML file exists
YAML_FILE="ray-job.recommendations-training.yaml"
if [ ! -f "$YAML_FILE" ]; then
    echo "❌ RayJob YAML file not found: $YAML_FILE"
    exit 1
fi

# Check if KubeRay operator is installed
echo "🔍 Checking if KubeRay operator is installed..."
if ! kubectl get crd rayjobs.ray.io &> /dev/null; then
    echo "❌ KubeRay operator is not installed. Please install it first:"
    echo "   helm repo add kuberay https://ray-project.github.io/kuberay-helm/"
    echo "   helm install kuberay-operator kuberay/kuberay-operator --version 1.0.0"
    exit 1
fi

# Check if there's an existing job and delete it
echo "🧹 Cleaning up any existing recommendation training job..."
if kubectl get rayjob rayjob-recommendations-training &> /dev/null; then
    echo "   Deleting existing job..."
    kubectl delete rayjob rayjob-recommendations-training
    echo "   Waiting for cleanup..."
    sleep 10
fi

# Check if ConfigMap exists and recreate it with latest script
echo "📦 Setting up training script ConfigMap..."
if kubectl get configmap ray-training-script &> /dev/null; then
    echo "   Updating existing ConfigMap..."
    kubectl delete configmap ray-training-script
fi

# Create ConfigMap with the Kubernetes-compatible training script
TRAINING_SCRIPT="../ray-apps/train_recommendation_model_k8s.py"
if [ ! -f "$TRAINING_SCRIPT" ]; then
    echo "❌ Training script not found: $TRAINING_SCRIPT"
    exit 1
fi

kubectl create configmap ray-training-script --from-file="$TRAINING_SCRIPT"
echo "   ✅ ConfigMap created successfully"

# Deploy the new job
echo "📋 Deploying new recommendation training job..."
kubectl apply -f "$YAML_FILE"

# Wait for the job to start
echo "⏳ Waiting for job to start..."
kubectl wait --for=condition=JobDeploymentStatus --timeout=300s rayjob/rayjob-recommendations-training

# Show job status
echo "📊 Job status:"
kubectl get rayjob rayjob-recommendations-training

# Wait for job completion (timeout after 5 minutes)
echo "⏳ Waiting for job completion (timeout: 5 minutes)..."
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
                echo "   Job is still running..."
                sleep 10
                ;;
            *)
                echo "   Job status: $STATUS"
                sleep 5
                ;;
        esac
    done
' || echo "⏰ Timeout reached, but job may still be running"

# Show final status
echo ""
echo "📊 Final job status:"
kubectl get rayjob rayjob-recommendations-training

# Get job runner pod name
JOB_POD=$(kubectl get pods -l job-name --no-headers 2>/dev/null | grep rayjob-recommendations-training | awk '{print $1}' | head -1)

if [ -n "$JOB_POD" ]; then
    echo ""
    echo "📝 Training logs:"
    echo "=================="
    kubectl logs "$JOB_POD" 2>/dev/null | tail -20 || echo "Logs not available"
else
    echo ""
    echo "📝 To view training logs, find the job runner pod:"
    echo "   kubectl get pods | grep rayjob-recommendations-training"
    echo "   kubectl logs <job-runner-pod-name>"
fi

echo ""
echo "✅ Deployment completed!"
echo ""
echo "📋 Useful commands:"
echo "   Monitor job: kubectl get rayjob rayjob-recommendations-training"
echo "   View details: kubectl describe rayjob rayjob-recommendations-training"
echo "   View all pods: kubectl get pods | grep recommendation"
echo "   Delete job: kubectl delete rayjob rayjob-recommendations-training"
echo ""
echo "📊 Ray dashboard (if cluster is running):"
echo "   kubectl port-forward service/rayjob-recommendations-training-*-head-svc 8265:8265"
echo "   Then open: http://localhost:8265"
