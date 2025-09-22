#!/bin/bash

# Complete Kubernetes Deployment Script for E-commerce Platform
# This script deploys all services (MinIO, Nessie, Spark, Flink, Ray) to Kubernetes

set -e

echo "🚀 E-commerce Platform - Complete Kubernetes Deployment"
echo "========================================================"

# Configuration
NAMESPACE="ecommerce-platform"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="${SCRIPT_DIR}/../k8s"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is not installed or not in PATH"
    exit 1
fi

echo "✅ kubectl is available"

# Check if we can connect to Kubernetes cluster
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Cannot connect to Kubernetes cluster. Please ensure your cluster is running and kubeconfig is set up."
    exit 1
fi

echo "✅ Connected to Kubernetes cluster"

# Function to wait for deployment to be ready
wait_for_deployment() {
    local deployment=$1
    local namespace=$2
    echo "   ⏳ Waiting for deployment $deployment to be ready..."
    kubectl rollout status deployment/$deployment -n $namespace --timeout=300s
    echo "   ✅ Deployment $deployment is ready"
}

# Function to wait for pods to be running
wait_for_pods() {
    local selector=$1
    local namespace=$2
    echo "   ⏳ Waiting for pods with selector $selector to be running..."
    kubectl wait --for=condition=Ready pods -l $selector -n $namespace --timeout=300s
    echo "   ✅ Pods are ready"
}

# Step 1: Create namespace
echo ""
echo "📦 Step 1: Creating namespace..."
kubectl apply -f "${K8S_DIR}/namespace.yaml"
echo "   ✅ Namespace created"

# Step 2: Deploy MinIO (Object Storage)
echo ""
echo "🗄️  Step 2: Deploying MinIO..."
kubectl apply -f "${K8S_DIR}/minio.yaml"
wait_for_deployment "minio" $NAMESPACE

# Step 3: Deploy Nessie (Iceberg Catalog)
echo ""
echo "📊 Step 3: Deploying Nessie..."
kubectl apply -f "${K8S_DIR}/nessie.yaml"
wait_for_deployment "nessie" $NAMESPACE

# Step 4: Create application ConfigMaps
echo ""
echo "⚙️  Step 4: Creating application ConfigMaps..."

# Create Spark apps ConfigMap
kubectl create configmap spark-apps \
    --from-file="${K8S_DIR}/spark-apps/" \
    -n $NAMESPACE \
    --dry-run=client -o yaml | kubectl apply -f -

# Create Flink apps ConfigMap
kubectl create configmap flink-apps \
    --from-file="${K8S_DIR}/flink-apps/" \
    -n $NAMESPACE \
    --dry-run=client -o yaml | kubectl apply -f -

# Create Ray training script ConfigMap
kubectl create configmap ray-training-script \
    --from-file="${K8S_DIR}/ray-apps/train_recommendation_model_k8s.py" \
    -n $NAMESPACE \
    --dry-run=client -o yaml | kubectl apply -f -

echo "   ✅ ConfigMaps created"

# Step 5: Deploy Spark Cluster
echo ""
echo "⚡ Step 5: Deploying Spark cluster..."
kubectl apply -f "${K8S_DIR}/spark.yaml"
wait_for_deployment "spark-master" $NAMESPACE
wait_for_deployment "spark-worker" $NAMESPACE

# Step 6: Deploy Flink Cluster
echo ""
echo "🌊 Step 6: Deploying Flink cluster..."
kubectl apply -f "${K8S_DIR}/flink.yaml"
wait_for_deployment "flink-jobmanager" $NAMESPACE
wait_for_deployment "flink-taskmanager" $NAMESPACE

# Check if KubeRay operator is installed
echo ""
echo "🔍 Step 7: Checking KubeRay operator..."
if ! kubectl get crd rayjobs.ray.io &> /dev/null; then
    echo "⚠️  KubeRay operator is not installed. Installing it now..."
    echo "   Adding KubeRay Helm repository..."
    helm repo add kuberay https://ray-project.github.io/kuberay-helm/ || true
    helm repo update
    echo "   Installing KubeRay operator..."
    helm install kuberay-operator kuberay/kuberay-operator --version 1.0.0 --create-namespace || true
    echo "   Waiting for KubeRay operator to be ready..."
    kubectl wait --for=condition=Available deployment/kuberay-operator --timeout=300s
else
    echo "   ✅ KubeRay operator is already installed"
fi

# Step 8: Deploy Ray Cluster (for training jobs)
echo ""
echo "🧠 Step 8: Deploying Ray cluster..."
kubectl apply -f "${K8S_DIR}/ray.yaml"

# Give some time for Ray cluster to initialize
echo "   ⏳ Waiting for Ray cluster to initialize..."
sleep 30

# Step 9: Verify all deployments
echo ""
echo "🔍 Step 9: Verifying deployments..."

# Check all pods
echo "   Checking all pods in namespace $NAMESPACE:"
kubectl get pods -n $NAMESPACE

echo ""
echo "   Checking all services in namespace $NAMESPACE:"
kubectl get services -n $NAMESPACE

echo ""
echo "✅ Deployment completed successfully!"
echo ""
echo "📋 Access Information:"
echo "   MinIO Console: kubectl port-forward svc/minio 9001:9001 -n $NAMESPACE"
echo "   MinIO API: kubectl port-forward svc/minio 9000:9000 -n $NAMESPACE"
echo "   Nessie API: kubectl port-forward svc/nessie 19120:19120 -n $NAMESPACE"
echo "   Spark Master UI: kubectl port-forward svc/spark-master 8080:8080 -n $NAMESPACE"
echo "   Flink JobManager UI: kubectl port-forward svc/flink-jobmanager 8081:8081 -n $NAMESPACE"
echo ""
echo "📝 Next Steps:"
echo "   1. Run validation tests: ./validate-deployment.sh"
echo "   2. Submit sample jobs: ./submit-sample-jobs.sh"
echo "   3. Monitor cluster health: kubectl get all -n $NAMESPACE"
echo ""
echo "🗑️  To clean up: ./cleanup-deployment.sh"