#!/bin/bash

# Kubernetes Deployment Validation Script
# This script validates that all services are running correctly in the Kubernetes cluster

set -e

echo "🔍 E-commerce Platform - Kubernetes Deployment Validation"
echo "=========================================================="

NAMESPACE="ecommerce-platform"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
            echo -e "   ${GREEN}✅ $message${NC}"
            ;;
        "FAIL")
            echo -e "   ${RED}❌ $message${NC}"
            ;;
        "WARN")
            echo -e "   ${YELLOW}⚠️  $message${NC}"
            ;;
    esac
}

# Function to check if kubectl is available
check_kubectl() {
    if command -v kubectl &> /dev/null; then
        print_status "PASS" "kubectl is available"
        return 0
    else
        print_status "FAIL" "kubectl is not installed or not in PATH"
        return 1
    fi
}

# Function to check cluster connectivity
check_cluster() {
    if kubectl cluster-info &> /dev/null; then
        print_status "PASS" "Connected to Kubernetes cluster"
        return 0
    else
        print_status "FAIL" "Cannot connect to Kubernetes cluster"
        return 1
    fi
}

# Function to check namespace
check_namespace() {
    if kubectl get namespace $NAMESPACE &> /dev/null; then
        print_status "PASS" "Namespace '$NAMESPACE' exists"
        return 0
    else
        print_status "FAIL" "Namespace '$NAMESPACE' does not exist"
        return 1
    fi
}

# Function to check deployment status
check_deployment() {
    local deployment=$1
    local expected_replicas=${2:-1}
    
    if kubectl get deployment $deployment -n $NAMESPACE &> /dev/null; then
        local ready_replicas=$(kubectl get deployment $deployment -n $NAMESPACE -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        if [[ "$ready_replicas" -ge "$expected_replicas" ]]; then
            print_status "PASS" "Deployment '$deployment' is ready ($ready_replicas/$expected_replicas replicas)"
            return 0
        else
            print_status "FAIL" "Deployment '$deployment' is not ready ($ready_replicas/$expected_replicas replicas)"
            return 1
        fi
    else
        print_status "FAIL" "Deployment '$deployment' not found"
        return 1
    fi
}

# Function to check service status
check_service() {
    local service=$1
    
    if kubectl get service $service -n $NAMESPACE &> /dev/null; then
        local cluster_ip=$(kubectl get service $service -n $NAMESPACE -o jsonpath='{.spec.clusterIP}')
        if [[ "$cluster_ip" != "None" && "$cluster_ip" != "" ]]; then
            print_status "PASS" "Service '$service' is available (ClusterIP: $cluster_ip)"
            return 0
        elif [[ "$cluster_ip" == "None" ]]; then
            print_status "PASS" "Service '$service' is available (Headless service)"
            return 0
        else
            print_status "FAIL" "Service '$service' has no ClusterIP"
            return 1
        fi
    else
        print_status "FAIL" "Service '$service' not found"
        return 1
    fi
}

# Function to check pod health
check_pod_health() {
    local selector=$1
    local service_name=$2
    
    local pods=$(kubectl get pods -l $selector -n $NAMESPACE --no-headers 2>/dev/null || echo "")
    if [[ -z "$pods" ]]; then
        print_status "FAIL" "No pods found for $service_name"
        return 1
    fi
    
    local total_pods=$(echo "$pods" | wc -l)
    local running_pods=$(echo "$pods" | grep -c "Running" || echo "0")
    
    if [[ "$running_pods" -eq "$total_pods" ]]; then
        print_status "PASS" "$service_name pods are healthy ($running_pods/$total_pods running)"
        return 0
    else
        print_status "FAIL" "$service_name pods are not healthy ($running_pods/$total_pods running)"
        return 1
    fi
}

# Function to test service connectivity
test_service_connectivity() {
    local service=$1
    local port=$2
    local endpoint=${3:-"/"}
    local protocol=${4:-"http"}
    
    echo "   Testing connectivity to $service:$port$endpoint..."
    
    # Create a temporary pod for testing
    local test_pod="connectivity-test-$(date +%s)"
    kubectl run $test_pod -n $NAMESPACE --image=curlimages/curl:latest --rm -i --restart=Never -- \
        curl -s --connect-timeout 10 --max-time 30 "$protocol://$service:$port$endpoint" > /dev/null 2>&1
    
    local exit_code=$?
    if [[ $exit_code -eq 0 ]]; then
        print_status "PASS" "$service is responding on port $port"
        return 0
    else
        print_status "FAIL" "$service is not responding on port $port"
        return 1
    fi
}

# Function to check persistent volumes
check_persistent_volumes() {
    echo ""
    echo "📦 Checking Persistent Volumes..."
    
    local pvc_list=$(kubectl get pvc -n $NAMESPACE --no-headers 2>/dev/null || echo "")
    if [[ -z "$pvc_list" ]]; then
        print_status "WARN" "No Persistent Volume Claims found"
        return 1
    fi
    
    while IFS= read -r line; do
        local pvc_name=$(echo "$line" | awk '{print $1}')
        local status=$(echo "$line" | awk '{print $2}')
        
        if [[ "$status" == "Bound" ]]; then
            print_status "PASS" "PVC '$pvc_name' is bound"
        else
            print_status "FAIL" "PVC '$pvc_name' is not bound (status: $status)"
        fi
    done <<< "$pvc_list"
}

# Main validation function
main() {
    local failed_checks=0
    
    echo "🔧 Checking Prerequisites..."
    check_kubectl || ((failed_checks++))
    check_cluster || ((failed_checks++))
    check_namespace || ((failed_checks++))
    
    echo ""
    echo "🗄️  Checking Storage Services..."
    check_deployment "minio" 1 || ((failed_checks++))
    check_service "minio" || ((failed_checks++))
    check_pod_health "app=minio" "MinIO" || ((failed_checks++))
    
    echo ""
    echo "📊 Checking Catalog Services..."
    check_deployment "nessie" 1 || ((failed_checks++))
    check_service "nessie" || ((failed_checks++))
    check_pod_health "app=nessie" "Nessie" || ((failed_checks++))
    
    echo ""
    echo "⚡ Checking Spark Cluster..."
    check_deployment "spark-master" 1 || ((failed_checks++))
    check_deployment "spark-worker" 2 || ((failed_checks++))
    check_service "spark-master" || ((failed_checks++))
    check_pod_health "app=spark,component=master" "Spark Master" || ((failed_checks++))
    check_pod_health "app=spark,component=worker" "Spark Workers" || ((failed_checks++))
    
    echo ""
    echo "🌊 Checking Flink Cluster..."
    check_deployment "flink-jobmanager" 1 || ((failed_checks++))
    check_deployment "flink-taskmanager" 2 || ((failed_checks++))
    check_service "flink-jobmanager" || ((failed_checks++))
    check_pod_health "app=flink,component=jobmanager" "Flink JobManager" || ((failed_checks++))
    check_pod_health "app=flink,component=taskmanager" "Flink TaskManagers" || ((failed_checks++))
    
    echo ""
    echo "🧠 Checking Ray Services..."
    if kubectl get crd rayjobs.ray.io &> /dev/null; then
        print_status "PASS" "KubeRay operator is installed"
        
        # Check if Ray job exists
        if kubectl get rayjob rayjob-recommendations-training -n $NAMESPACE &> /dev/null; then
            local job_status=$(kubectl get rayjob rayjob-recommendations-training -n $NAMESPACE -o jsonpath='{.status.jobStatus}' 2>/dev/null || echo "Unknown")
            print_status "PASS" "Ray job exists (status: $job_status)"
        else
            print_status "WARN" "Ray job not found (this is normal if not yet deployed)"
        fi
    else
        print_status "FAIL" "KubeRay operator is not installed"
        ((failed_checks++))
    fi
    
    check_persistent_volumes
    
    echo ""
    echo "🌐 Testing Service Connectivity..."
    test_service_connectivity "minio" "9000" "/minio/health/live" || ((failed_checks++))
    test_service_connectivity "nessie" "19120" "/api/v1/config" || ((failed_checks++))
    test_service_connectivity "spark-master" "8080" "/" || ((failed_checks++))
    test_service_connectivity "flink-jobmanager" "8081" "/" || ((failed_checks++))
    
    echo ""
    echo "📋 Summary:"
    if [[ $failed_checks -eq 0 ]]; then
        print_status "PASS" "All validation checks passed! The platform is ready for use."
        echo ""
        echo "🚀 Next steps:"
        echo "   - Access MinIO Console: kubectl port-forward svc/minio 9001:9001 -n $NAMESPACE"
        echo "   - Access Spark UI: kubectl port-forward svc/spark-master 8080:8080 -n $NAMESPACE"
        echo "   - Access Flink UI: kubectl port-forward svc/flink-jobmanager 8081:8081 -n $NAMESPACE"
        echo "   - Submit jobs: ./submit-sample-jobs.sh"
        exit 0
    else
        print_status "FAIL" "$failed_checks validation checks failed. Please review the issues above."
        echo ""
        echo "🔧 Troubleshooting tips:"
        echo "   - Check pod logs: kubectl logs -l app=<service> -n $NAMESPACE"
        echo "   - Check events: kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp'"
        echo "   - Check resource usage: kubectl top pods -n $NAMESPACE"
        exit 1
    fi
}

# Run main function
main "$@"