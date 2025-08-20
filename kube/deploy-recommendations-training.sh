#!/bin/bash

# Deploy Ray Recommendations Training Job to Kubernetes
# This script deploys the recommendation model training job to your Ray Kubernetes cluster

set -e

echo "🚀 Deploying Ray Recommendations Training Job..."

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is not installed or not in PATH"
    exit 1
fi

# Check if the RayJob YAML file exists
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

# Deploy the new job
echo "📋 Deploying new recommendation training job..."
kubectl apply -f "$YAML_FILE"

# Wait for the job to start
echo "⏳ Waiting for job to start..."
kubectl wait --for=condition=JobDeploymentStatus --timeout=300s rayjob/rayjob-recommendations-training

# Show job status
echo "📊 Job status:"
kubectl get rayjob rayjob-recommendations-training

# Show how to monitor the job
echo ""
echo "✅ Recommendation training job deployed successfully!"
echo ""
echo "📋 To monitor the job:"
echo "   kubectl get rayjob rayjob-recommendations-training"
echo "   kubectl describe rayjob rayjob-recommendations-training"
echo ""
echo "📊 To view Ray dashboard:"
echo "   kubectl port-forward service/rayjob-recommendations-training-raycluster-head-svc 8265:8265"
echo "   Then open: http://localhost:8265"
echo ""
echo "📝 To view job logs:"
echo "   kubectl logs -l ray.io/cluster=rayjob-recommendations-training-raycluster"
echo ""
echo "🗑️  To delete the job:"
echo "   kubectl delete rayjob rayjob-recommendations-training"
