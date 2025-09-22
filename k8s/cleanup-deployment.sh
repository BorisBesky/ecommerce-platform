#!/bin/bash

# Cleanup Kubernetes Deployment Script
# This script removes all deployed services from the Kubernetes cluster

set -e

echo "🗑️  E-commerce Platform - Kubernetes Cleanup"
echo "=============================================="

NAMESPACE="ecommerce-platform"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is not installed or not in PATH"
    exit 1
fi

echo "⚠️  WARNING: This will delete all resources in namespace '$NAMESPACE'"
echo "This includes:"
echo "   - All deployments and pods"
echo "   - All services"
echo "   - All persistent volume claims and data"
echo "   - All ConfigMaps"
echo "   - The entire namespace"
echo ""

read -p "Are you sure you want to continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cleanup cancelled."
    exit 0
fi

echo ""
echo "🧹 Starting cleanup..."

# Step 1: Delete Ray jobs first (if any)
echo "🧠 Cleaning up Ray jobs..."
if kubectl get rayjob -n $NAMESPACE &> /dev/null; then
    kubectl delete rayjob --all -n $NAMESPACE || true
    echo "   ✅ Ray jobs deleted"
else
    echo "   ℹ️  No Ray jobs found"
fi

# Step 2: Delete all other resources in the namespace
echo ""
echo "📦 Deleting all resources in namespace '$NAMESPACE'..."
if kubectl get namespace $NAMESPACE &> /dev/null; then
    # Delete deployments
    kubectl delete deployments --all -n $NAMESPACE || true
    
    # Delete services
    kubectl delete services --all -n $NAMESPACE || true
    
    # Delete configmaps
    kubectl delete configmaps --all -n $NAMESPACE || true
    
    # Delete persistent volume claims
    kubectl delete pvc --all -n $NAMESPACE || true
    
    # Wait a moment for resources to be cleaned up
    echo "   ⏳ Waiting for resources to be cleaned up..."
    sleep 10
    
    # Delete the namespace
    kubectl delete namespace $NAMESPACE || true
    
    echo "   ✅ Namespace '$NAMESPACE' and all resources deleted"
else
    echo "   ℹ️  Namespace '$NAMESPACE' not found"
fi

# Step 3: Optional - Clean up KubeRay operator
echo ""
echo "🤖 KubeRay Operator:"
echo "The KubeRay operator is still installed and can be used for other Ray workloads."
echo "If you want to remove it completely, run:"
echo "   helm uninstall kuberay-operator"

echo ""
echo "✅ Cleanup completed!"
echo ""
echo "ℹ️  To redeploy the platform, run: ./deploy-all.sh"