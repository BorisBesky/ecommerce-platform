#!/bin/bash
# Script to run e2e tests against a deployed clickstream service

set -e

echo "🧪 Running E2E Tests for Clickstream Service"
echo "=============================================="

# Configuration
NAMESPACE="${K8S_NAMESPACE:-ecommerce-platform}"
SERVICE_NAME="clickstream-backend"
SERVICE_PORT="8000"
LOCAL_PORT="${LOCAL_PORT:-8000}"
CLICKSTREAM_BASE_URL="${CLICKSTREAM_BASE_URL:-http://localhost:${LOCAL_PORT}}"

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
        "INFO")
            echo -e "${BLUE}ℹ ${message}${NC}"
            ;;
        "SUCCESS")
            echo -e "${GREEN}✅ ${message}${NC}"
            ;;
        "ERROR")
            echo -e "${RED}❌ ${message}${NC}"
            ;;
        "WARN")
            echo -e "${YELLOW}⚠️  ${message}${NC}"
            ;;
    esac
}

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    print_status "ERROR" "kubectl is not installed or not in PATH"
    exit 1
fi

# Check if pytest is available
if ! command -v pytest &> /dev/null; then
    print_status "ERROR" "pytest is not installed. Install with: pip install -r requirements-test.txt"
    exit 1
fi

# Function to check if service is deployed
check_service_deployed() {
    if kubectl get service "$SERVICE_NAME" -n "$NAMESPACE" &> /dev/null; then
        print_status "SUCCESS" "Service $SERVICE_NAME found in namespace $NAMESPACE"
        return 0
    else
        print_status "ERROR" "Service $SERVICE_NAME not found in namespace $NAMESPACE"
        return 1
    fi
}

# Function to setup port forwarding
setup_port_forward() {
    print_status "INFO" "Setting up port forwarding to $SERVICE_NAME..."
    
    # Check if service is already accessible (test the actual connection)
    if curl -s --connect-timeout 2 "${CLICKSTREAM_BASE_URL}/api/v1/health/live" &> /dev/null; then
        print_status "SUCCESS" "Service is already accessible at ${CLICKSTREAM_BASE_URL}"
        return 0
    fi
    
    # Kill any existing port-forward on this port
    if lsof -Pi :${LOCAL_PORT} -sTCP:LISTEN -t &> /dev/null; then
        print_status "WARN" "Port ${LOCAL_PORT} is in use. Attempting to free it..."
        local pids=$(lsof -Pi :${LOCAL_PORT} -sTCP:LISTEN -t)
        for pid in $pids; do
            # Check if it's a kubectl port-forward
            if ps -p $pid -o comm= | grep -q kubectl; then
                print_status "INFO" "Killing existing kubectl port-forward (PID: $pid)"
                kill $pid 2>/dev/null || true
                sleep 2
            else
                print_status "ERROR" "Port ${LOCAL_PORT} is in use by another process (PID: $pid). Please free the port first."
                return 1
            fi
        done
    fi
    
    # Start port forwarding in background
    kubectl port-forward "svc/$SERVICE_NAME" "${LOCAL_PORT}:${SERVICE_PORT}" -n "$NAMESPACE" &> /tmp/clickstream-port-forward.log &
    PORT_FORWARD_PID=$!
    
    # Wait for port forwarding to be ready
    print_status "INFO" "Waiting for port forwarding to be ready (PID: $PORT_FORWARD_PID)..."
    for i in {1..30}; do
        if curl -s --connect-timeout 2 "${CLICKSTREAM_BASE_URL}/api/v1/health/live" &> /dev/null; then
            print_status "SUCCESS" "Port forwarding is ready"
            return 0
        fi
        # Check if port-forward process is still running
        if ! ps -p $PORT_FORWARD_PID &> /dev/null; then
            print_status "ERROR" "Port forwarding process died. Check logs at /tmp/clickstream-port-forward.log"
            cat /tmp/clickstream-port-forward.log
            return 1
        fi
        sleep 1
    done
    
    print_status "ERROR" "Port forwarding failed to establish within 30 seconds"
    print_status "INFO" "Port-forward logs:"
    cat /tmp/clickstream-port-forward.log
    return 1
}

# Function to cleanup
cleanup() {
    if [ -n "$PORT_FORWARD_PID" ]; then
        if ps -p $PORT_FORWARD_PID &> /dev/null; then
            print_status "INFO" "Stopping port forwarding (PID: $PORT_FORWARD_PID)..."
            kill $PORT_FORWARD_PID 2>/dev/null || true
            sleep 1
            # Force kill if still running
            if ps -p $PORT_FORWARD_PID &> /dev/null; then
                kill -9 $PORT_FORWARD_PID 2>/dev/null || true
            fi
        fi
    fi
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Main execution
main() {
    print_status "INFO" "Configuration:"
    echo "  Namespace: $NAMESPACE"
    echo "  Service: $SERVICE_NAME"
    echo "  Service Port: $SERVICE_PORT"
    echo "  Local Port: $LOCAL_PORT"
    echo "  Base URL: $CLICKSTREAM_BASE_URL"
    echo ""
    
    # Check if service is deployed
    if ! check_service_deployed; then
        print_status "ERROR" "Cannot run e2e tests - service not deployed"
        exit 1
    fi
    
    # Setup port forwarding if needed
    if [[ "$CLICKSTREAM_BASE_URL" == *"localhost"* ]] || [[ "$CLICKSTREAM_BASE_URL" == *"127.0.0.1"* ]]; then
        if ! setup_port_forward; then
            print_status "ERROR" "Failed to setup port forwarding"
            exit 1
        fi
    fi
    
    # Run the tests
    print_status "INFO" "Running e2e tests..."
    echo ""
    
    cd "$(dirname "$0")/.."
    
    export RUN_E2E_TESTS=true
    export CLICKSTREAM_BASE_URL="$CLICKSTREAM_BASE_URL"
    
    # Check if pytest-cov is installed and add coverage if available
    PYTEST_ARGS="-v --tb=short --color=yes"
    if python3 -c "import pytest_cov" 2>/dev/null; then
        PYTEST_ARGS="$PYTEST_ARGS --cov=app --cov-report=term-missing"
    fi
    
    if pytest tests/test_e2e.py $PYTEST_ARGS; then
        echo ""
        print_status "SUCCESS" "All e2e tests passed!"
        exit 0
    else
        echo ""
        print_status "ERROR" "Some e2e tests failed"
        exit 1
    fi
}

# Run main function
main "$@"

