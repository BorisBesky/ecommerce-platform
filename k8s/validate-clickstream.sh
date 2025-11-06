#!/bin/bash

# Clickstream Service Validation Script
# This script validates the clickstream service deployment and runs e2e tests

set -e

echo "🔍 Clickstream Service - Deployment Validation & E2E Tests"
echo "==========================================================="

NAMESPACE="${K8S_NAMESPACE:-ecommerce-platform}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_E2E="${RUN_E2E_TESTS:-true}"
LOCAL_PORT="${LOCAL_PORT:-8000}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
        "INFO")
            echo -e "   ${BLUE}ℹ $message${NC}"
            ;;
    esac
}

# Check prerequisites
check_prerequisites() {
    echo ""
    echo "🔧 Checking Prerequisites..."
    
    local failed=0
    
    if command -v kubectl &> /dev/null; then
        print_status "PASS" "kubectl is available"
    else
        print_status "FAIL" "kubectl is not installed or not in PATH"
        ((failed++))
    fi
    
    if kubectl cluster-info &> /dev/null; then
        print_status "PASS" "Connected to Kubernetes cluster"
    else
        print_status "FAIL" "Cannot connect to Kubernetes cluster"
        ((failed++))
    fi
    
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        print_status "PASS" "Namespace '$NAMESPACE' exists"
    else
        print_status "FAIL" "Namespace '$NAMESPACE' does not exist"
        ((failed++))
    fi
    
    return $failed
}

# Check deployment status
check_deployment() {
    local deployment=$1
    local expected_replicas=${2:-1}
    
    if kubectl get deployment "$deployment" -n "$NAMESPACE" &> /dev/null; then
        local ready_replicas=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
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

# Check service status
check_service() {
    local service=$1
    
    if kubectl get service "$service" -n "$NAMESPACE" &> /dev/null; then
        local cluster_ip=$(kubectl get service "$service" -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}')
        if [[ "$cluster_ip" != "" ]]; then
            print_status "PASS" "Service '$service' is available (ClusterIP: $cluster_ip)"
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

# Check pod health
check_pod_health() {
    local selector=$1
    local service_name=$2
    
    local pods=$(kubectl get pods -l "$selector" -n "$NAMESPACE" --no-headers 2>/dev/null || echo "")
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
        # Show pod status
        echo "$pods" | while read -r line; do
            local pod_name=$(echo "$line" | awk '{print $1}')
            local status=$(echo "$line" | awk '{print $3}')
            print_status "INFO" "  Pod: $pod_name - Status: $status"
        done
        return 1
    fi
}

# Test service connectivity
test_service_connectivity() {
    local service=$1
    local port=$2
    local endpoint=${3:-"/"}
    
    print_status "INFO" "Testing connectivity to $service:$port$endpoint..."
    
    # Create a temporary pod for testing
    local test_pod="connectivity-test-$(date +%s)"
    if kubectl run "$test_pod" -n "$NAMESPACE" --image=curlimages/curl:latest --rm -i --restart=Never -- \
        curl -s --connect-timeout 10 --max-time 30 "http://$service:$port$endpoint" > /dev/null 2>&1; then
        print_status "PASS" "$service is responding on port $port"
        return 0
    else
        print_status "FAIL" "$service is not responding on port $port"
        return 1
    fi
}

# Check configuration
check_configuration() {
    echo ""
    echo "⚙️ Checking Configuration..."
    
    local failed=0
    
    # Check ConfigMap
    if kubectl get configmap clickstream-service-config -n "$NAMESPACE" &> /dev/null; then
        print_status "PASS" "ConfigMap 'clickstream-service-config' exists"
    else
        print_status "FAIL" "ConfigMap 'clickstream-service-config' not found"
        ((failed++))
    fi
    
    # Check Secret
    if kubectl get secret clickstream-service-secrets -n "$NAMESPACE" &> /dev/null; then
        print_status "PASS" "Secret 'clickstream-service-secrets' exists"
    else
        print_status "FAIL" "Secret 'clickstream-service-secrets' not found"
        ((failed++))
    fi
    
    return $failed
}

# Run e2e tests
run_e2e_tests() {
    echo ""
    echo "🧪 Running E2E Tests..."
    
    # Check if Python and pytest are available
    if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
        print_status "WARN" "Python not found. Skipping e2e tests."
        return 1
    fi
    
    local python_cmd=$(command -v python3 || command -v python)
    
    if ! $python_cmd -m pytest --version &> /dev/null; then
        print_status "WARN" "pytest not installed. Skipping e2e tests."
        print_status "INFO" "Install with: pip install pytest httpx"
        return 1
    fi
    
    # Run the e2e test script
    local test_script="${SCRIPT_DIR}/../services/clickstream/backend/tests/run_e2e_tests.sh"
    if [[ -f "$test_script" ]]; then
        export K8S_NAMESPACE="$NAMESPACE"
        export LOCAL_PORT="$LOCAL_PORT"
        bash "$test_script"
        return $?
    else
        print_status "WARN" "E2E test script not found at $test_script"
        return 1
    fi
}

# Main validation
main() {
    local failed_checks=0
    
    check_prerequisites || ((failed_checks+=$?))
    
    echo ""
    echo "📊 Checking Clickstream Deployments..."
    check_deployment "clickstream-backend" 1 || ((failed_checks++))
    check_deployment "clickstream-frontend" 1 || ((failed_checks++))
    
    echo ""
    echo "🌐 Checking Clickstream Services..."
    check_service "clickstream-backend" || ((failed_checks++))
    check_service "clickstream-frontend" || ((failed_checks++))
    
    echo ""
    echo "🏥 Checking Pod Health..."
    check_pod_health "app=clickstream,component=backend" "Clickstream Backend" || ((failed_checks++))
    check_pod_health "app=clickstream,component=frontend" "Clickstream Frontend" || ((failed_checks++))
    
    check_configuration || ((failed_checks+=$?))
    
    echo ""
    echo "🔌 Testing Service Connectivity..."
    test_service_connectivity "clickstream-backend" "8000" "/api/v1/health/live" || ((failed_checks++))
    test_service_connectivity "clickstream-frontend" "80" "/" || ((failed_checks++))
    
    echo ""
    echo "📋 Deployment Validation Summary:"
    if [[ $failed_checks -eq 0 ]]; then
        print_status "PASS" "All deployment validation checks passed!"
        
        if [[ "$RUN_E2E" == "true" ]]; then
            if run_e2e_tests; then
                echo ""
                print_status "PASS" "All e2e tests passed!"
            else
                echo ""
                print_status "WARN" "E2E tests completed with warnings/failures"
            fi
        else
            echo ""
            print_status "INFO" "Skipping e2e tests (set RUN_E2E_TESTS=true to enable)"
        fi
        
        echo ""
        echo "🚀 Clickstream Service is ready!"
        echo ""
        echo "Access the service:"
        echo "   Frontend: kubectl port-forward svc/clickstream-frontend $((LOCAL_PORT+1)):80 -n $NAMESPACE"
        echo "   Backend:  kubectl port-forward svc/clickstream-backend $LOCAL_PORT:8000 -n $NAMESPACE"
        echo "   API Docs: http://localhost:$LOCAL_PORT/docs"
        exit 0
    else
        print_status "FAIL" "$failed_checks validation checks failed"
        echo ""
        echo "🔧 Troubleshooting:"
        echo "   Check logs: kubectl logs -l app=clickstream -n $NAMESPACE"
        echo "   Check events: kubectl get events -n $NAMESPACE | grep clickstream"
        echo "   Check pods: kubectl get pods -l app=clickstream -n $NAMESPACE"
        exit 1
    fi
}

# Run main
main "$@"

