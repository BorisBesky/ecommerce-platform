#!/bin/bash

# Prerequisites Check Script
# This script verifies that all prerequisites are met before deploying the platform

set -e

echo "🔍 E-commerce Platform - Prerequisites Check"
echo "=============================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    case $status in
        "PASS")
            echo -e "${GREEN}✅ $message${NC}"
            ;;
        "FAIL")
            echo -e "${RED}❌ $message${NC}"
            ;;
        "WARN")
            echo -e "${YELLOW}⚠️  $message${NC}"
            ;;
        "INFO")
            echo -e "ℹ️  $message"
            ;;
    esac
}

failed_checks=0

echo "🛠️  Checking Required Tools..."

# Check kubectl
if command -v kubectl &> /dev/null; then
    print_status "PASS" "kubectl is installed"
    kubectl_version=$(kubectl version --client --short 2>/dev/null | cut -d' ' -f3 || echo "unknown")
    print_status "INFO" "kubectl version: $kubectl_version"
else
    print_status "FAIL" "kubectl is not installed"
    echo "   Install kubectl: https://kubernetes.io/docs/tasks/tools/"
    ((failed_checks++))
fi

# Check helm
if command -v helm &> /dev/null; then
    print_status "PASS" "helm is installed"
    helm_version=$(helm version --short 2>/dev/null || echo "unknown")
    print_status "INFO" "helm version: $helm_version"
else
    print_status "WARN" "helm is not installed (required for KubeRay operator)"
    echo "   Install helm: https://helm.sh/docs/intro/install/"
fi

# Check docker (for local development)
if command -v docker &> /dev/null; then
    print_status "PASS" "docker is installed"
else
    print_status "WARN" "docker is not installed (optional, useful for local development)"
fi

echo ""
echo "🏗️  Checking Kubernetes Cluster..."

# Check cluster connectivity
if kubectl cluster-info &> /dev/null; then
    print_status "PASS" "Connected to Kubernetes cluster"
    
    # Get cluster info
    cluster_name=$(kubectl config current-context 2>/dev/null || echo "unknown")
    print_status "INFO" "Current context: $cluster_name"
    
    # Check cluster version
    k8s_version=$(kubectl version 2>/dev/null | grep "Server Version" | cut -d' ' -f3 || echo "unknown")
    print_status "INFO" "Kubernetes version: $k8s_version"
    
else
    print_status "FAIL" "Cannot connect to Kubernetes cluster"
    echo "   Make sure your cluster is running and kubeconfig is set up correctly"
    echo "   For local development:"
    echo "     - Docker Desktop: Enable Kubernetes in settings"
    echo "     - Minikube: minikube start"
    echo "     - Kind: kind create cluster"
    ((failed_checks++))
fi

# Check node resources
if kubectl get nodes &> /dev/null; then
    echo ""
    echo "📊 Checking Cluster Resources..."
    
    node_count=$(kubectl get nodes --no-headers 2>/dev/null | wc -l)
    print_status "INFO" "Number of nodes: $node_count"
    
    # Check node status
    ready_nodes=$(kubectl get nodes --no-headers 2>/dev/null | grep -c " Ready " || echo "0")
    if [[ "$ready_nodes" -eq "$node_count" ]]; then
        print_status "PASS" "All nodes are ready ($ready_nodes/$node_count)"
    else
        print_status "FAIL" "Not all nodes are ready ($ready_nodes/$node_count)"
        ((failed_checks++))
    fi
    
    # Check if we can get node metrics (optional)
    if kubectl top nodes &> /dev/null; then
        print_status "PASS" "Metrics server is available"
        
        # Basic resource check
        total_cpu=$(kubectl get nodes -o jsonpath='{.items[*].status.allocatable.cpu}' | tr ' ' '\n' | sed 's/m//g' | awk '{sum += $1} END {print sum/1000}' 2>/dev/null || echo "unknown")
        total_memory=$(kubectl get nodes -o jsonpath='{.items[*].status.allocatable.memory}' | tr ' ' '\n' | sed 's/Ki//g' | awk '{sum += $1} END {print sum/1024/1024}' 2>/dev/null || echo "unknown")
        
        print_status "INFO" "Total allocatable CPU: ${total_cpu} cores"
        print_status "INFO" "Total allocatable memory: ${total_memory} GB"
        
        # Check if resources are sufficient
        if [[ "$total_cpu" != "unknown" ]] && (( $(echo "$total_cpu >= 8" | bc -l) )); then
            print_status "PASS" "Sufficient CPU resources for production deployment"
        elif [[ "$total_cpu" != "unknown" ]] && (( $(echo "$total_cpu >= 4" | bc -l) )); then
            print_status "WARN" "Limited CPU resources - suitable for development only"
        else
            print_status "WARN" "CPU resources may be insufficient"
        fi
        
        if [[ "$total_memory" != "unknown" ]] && (( $(echo "$total_memory >= 16" | bc -l) )); then
            print_status "PASS" "Sufficient memory for production deployment"
        elif [[ "$total_memory" != "unknown" ]] && (( $(echo "$total_memory >= 8" | bc -l) )); then
            print_status "WARN" "Limited memory - suitable for development only"
        else
            print_status "WARN" "Memory may be insufficient"
        fi
    else
        print_status "WARN" "Metrics server not available (resource monitoring disabled)"
    fi
fi

echo ""
echo "🔧 Checking Existing Resources..."

# Check if namespace already exists
if kubectl get namespace ecommerce-platform &> /dev/null; then
    print_status "WARN" "Namespace 'ecommerce-platform' already exists"
    echo "   You may want to clean up first: ./cleanup-deployment.sh"
else
    print_status "PASS" "Namespace 'ecommerce-platform' is available"
fi

# Check for conflicting services
conflicting_services=("minio" "nessie" "spark-master" "flink-jobmanager")
for service in "${conflicting_services[@]}"; do
    if kubectl get service "$service" -n ecommerce-platform &> /dev/null; then
        print_status "WARN" "Service '$service' already exists in ecommerce-platform namespace"
    fi
done

# Check storage class
default_storage_class=$(kubectl get storageclass --no-headers 2>/dev/null | grep "(default)" | awk '{print $1}' || echo "none")
if [[ "$default_storage_class" != "none" ]]; then
    print_status "PASS" "Default storage class available: $default_storage_class"
else
    print_status "WARN" "No default storage class found - PVCs may not be provisioned automatically"
    echo "   Available storage classes:"
    kubectl get storageclass --no-headers 2>/dev/null | awk '{print "     - " $1}' || echo "     (none found)"
fi

echo ""
echo "🔍 Checking Dependencies..."

# Check for Python
if command -v python3 &> /dev/null; then
    print_status "PASS" "Python 3 is available"
    python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
    print_status "INFO" "Python version: $python_version"
else
    print_status "WARN" "Python 3 not found (needed for validation scripts)"
fi

# Check for essential Python modules
python_modules=("yaml" "json")
for module in "${python_modules[@]}"; do
    if python3 -c "import $module" &> /dev/null; then
        print_status "PASS" "Python module '$module' is available"
    else
        print_status "WARN" "Python module '$module' not found"
    fi
done

echo ""
echo "📋 Summary:"
echo "==========="

if [[ $failed_checks -eq 0 ]]; then
    print_status "PASS" "All critical prerequisites are met!"
    echo ""
    echo "🚀 Ready to deploy! Run the following commands:"
    echo "   ./deploy-all.sh          # Deploy the complete platform"
    echo "   ./validate-deployment.sh # Validate after deployment"
    echo "   ./submit-sample-jobs.sh  # Test with sample workloads"
else
    print_status "FAIL" "$failed_checks critical issues found"
    echo ""
    echo "🔧 Please resolve the issues above before deploying the platform."
    echo ""
    echo "📚 Helpful resources:"
    echo "   - Kubernetes setup: https://kubernetes.io/docs/setup/"
    echo "   - kubectl installation: https://kubernetes.io/docs/tasks/tools/"
    echo "   - Helm installation: https://helm.sh/docs/intro/install/"
    exit 1
fi

echo ""
echo "💡 Optional enhancements:"
echo "   - Install metrics-server for resource monitoring"
echo "   - Configure ingress controller for external access"
echo "   - Set up monitoring with Prometheus/Grafana"
echo "   - Configure backup solutions for persistent data"