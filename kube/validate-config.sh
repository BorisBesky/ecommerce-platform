#!/bin/bash

# Validate Ray Recommendations Training Configuration
# This script validates the YAML configuration and checks prerequisites

set -e

echo "🔍 Validating Ray Recommendations Training Configuration..."

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is not installed or not in PATH"
    exit 1
else
    echo "✅ kubectl is available"
fi

# Check if the YAML file exists and is valid
YAML_FILE="ray-job.recommendations-training.yaml"
if [ ! -f "$YAML_FILE" ]; then
    echo "❌ RayJob YAML file not found: $YAML_FILE"
    exit 1
else
    echo "✅ RayJob YAML file found"
fi

# Validate YAML syntax
if kubectl apply --dry-run=client -f "$YAML_FILE" &> /dev/null; then
    echo "✅ YAML syntax is valid"
else
    echo "❌ YAML syntax validation failed"
    kubectl apply --dry-run=client -f "$YAML_FILE"
    exit 1
fi

# Check if training script exists
TRAINING_SCRIPT="../ray-apps/train_recommendation_model.py"
if [ ! -f "$TRAINING_SCRIPT" ]; then
    echo "❌ Training script not found: $TRAINING_SCRIPT"
    exit 1
else
    echo "✅ Training script found"
fi

# Check if clickstream data exists
DATA_DIR="../data"
if [ ! -d "$DATA_DIR" ]; then
    echo "❌ Data directory not found: $DATA_DIR"
    exit 1
fi

CLICKSTREAM_FILES=$(ls "$DATA_DIR"/clickstream-*.json 2>/dev/null | wc -l)
MERGED_FILE="$DATA_DIR/clickstream.json"

if [ "$CLICKSTREAM_FILES" -gt 0 ]; then
    echo "✅ Found $CLICKSTREAM_FILES clickstream files"
else
    echo "⚠️  No clickstream files found in $DATA_DIR"
fi

if [ -f "$MERGED_FILE" ]; then
    echo "✅ Merged clickstream file exists"
    RECORDS=$(wc -l < "$MERGED_FILE")
    echo "   📊 Contains $RECORDS records"
else
    echo "⚠️  Merged clickstream file not found. Run ../tools/prepare-data.py first"
fi

# Check if KubeRay CRDs are installed
echo "🔍 Checking KubeRay installation..."
if kubectl get crd rayjobs.ray.io &> /dev/null; then
    echo "✅ KubeRay CRDs are installed"
    
    # Check if KubeRay operator is running
    if kubectl get pods -l app.kubernetes.io/name=kuberay-operator 2>/dev/null | grep -q Running; then
        echo "✅ KubeRay operator is running"
    else
        echo "⚠️  KubeRay operator pods not found or not running"
    fi
else
    echo "❌ KubeRay CRDs not installed. Install KubeRay operator first:"
    echo "   helm repo add kuberay https://ray-project.github.io/kuberay-helm/"
    echo "   helm install kuberay-operator kuberay/kuberay-operator --version 1.0.0"
fi

# Check for existing RayJob
if kubectl get rayjob rayjob-recommendations-training &> /dev/null; then
    echo "⚠️  Existing recommendation training job found"
    echo "   Status: $(kubectl get rayjob rayjob-recommendations-training -o jsonpath='{.status.jobStatus}')"
    echo "   You may want to delete it first: kubectl delete rayjob rayjob-recommendations-training"
fi

# Check node resources
echo "🔍 Checking cluster resources..."
NODES=$(kubectl get nodes --no-headers | wc -l)
echo "   📊 Cluster has $NODES nodes"

# Get total allocatable CPU and memory
TOTAL_CPU=$(kubectl get nodes -o jsonpath='{.items[*].status.allocatable.cpu}' | tr ' ' '\n' | sed 's/m//g' | awk '{sum += $1} END {print sum/1000}')
TOTAL_MEM=$(kubectl get nodes -o jsonpath='{.items[*].status.allocatable.memory}' | tr ' ' '\n' | sed 's/Ki//g' | awk '{sum += $1} END {print sum/1024/1024}')

echo "   📊 Total allocatable: ${TOTAL_CPU}CPU, ${TOTAL_MEM}Gi memory"
echo "   📊 Job will request: ~5CPU, ~17Gi memory (head + 2 workers)"

if (( $(echo "$TOTAL_CPU >= 5" | bc -l) )) && (( $(echo "$TOTAL_MEM >= 17" | bc -l) )); then
    echo "✅ Sufficient cluster resources"
else
    echo "⚠️  May not have sufficient cluster resources"
fi

echo ""
echo "🎯 Validation Summary:"
echo "✅ Configuration validated successfully!"
echo ""
echo "📋 Next steps:"
if [ ! -f "$MERGED_FILE" ]; then
    echo "1. Run: ../tools/prepare-data.py"
fi
echo "2. Deploy: ./deploy-recommendations-training.sh"
echo "3. Monitor: kubectl get rayjob rayjob-recommendations-training"
