#!/bin/bash

# Kubernetes Deployment Validation Script
# This script validates that all services are running correctly in the Kubernetes cluster

set -e

echo "🔍 E-commerce Platform - Kubernetes Deployment Validation"
echo "=========================================================="

NAMESPACE="ecommerce-platform"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAY_DIAG=false

for arg in "$@"; do
    case $arg in
        --ray-diagnostics)
            RAY_DIAG=true
            shift
            ;;
    esac
done

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
            # --- Ray diagnostics helper functions (scoped inside main) ---
            check_ray_job() {
                local job_name=$1
                if ! kubectl get rayjob "$job_name" -n $NAMESPACE &> /dev/null; then
                    print_status "WARN" "RayJob '$job_name' not found (normal if not deployed)"
                    return
                fi
                local job_status
                job_status=$(kubectl get rayjob "$job_name" -n $NAMESPACE -o jsonpath='{.status.jobStatus}' 2>/dev/null || echo "Unknown")
                case "$job_status" in
                    RUNNING|SUCCEEDED)
                        print_status "PASS" "RayJob '$job_name' status: $job_status"
                        ;;
                    FAILED)
                        print_status "FAIL" "RayJob '$job_name' status: FAILED"
                        ;;
                    *)
                        print_status "WARN" "RayJob '$job_name' status: $job_status"
                        ;;
                esac

                # Associated RayCluster name (if already created)
                local rc_name
                rc_name=$(kubectl get rayjob "$job_name" -n $NAMESPACE -o jsonpath='{.status.rayClusterName}' 2>/dev/null || echo "")
                if [[ -n "$rc_name" ]]; then
                    local rc_state
                    rc_state=$(kubectl get raycluster "$rc_name" -n $NAMESPACE -o jsonpath='{.status.state}' 2>/dev/null || echo "Unknown")
                    print_status "WARN" "RayCluster '$rc_name' state: $rc_state"
                    # Summarize cluster pods
                    local cluster_pods
                    cluster_pods=$(kubectl get pods -n $NAMESPACE -l ray.io/cluster="$rc_name" --no-headers 2>/dev/null || true)
                    if [[ -n "$cluster_pods" ]]; then
                        local running pending failed
                        running=$(echo "$cluster_pods" | awk '$3=="Running"' | wc -l | tr -d ' ')
                        pending=$(echo "$cluster_pods" | awk '$3=="Pending"' | wc -l | tr -d ' ')
                        failed=$(echo "$cluster_pods" | awk '$3=="Error" || $3=="CrashLoopBackOff" || $3=="Failed"' | wc -l | tr -d ' ')
                        if [[ "$failed" -gt 0 || "$pending" -gt 0 ]]; then
                            print_status "WARN" "RayCluster pods: Running=$running Pending=$pending Failed=$failed"
                        else
                            print_status "PASS" "All RayCluster pods running ($running)"
                        fi
                    fi
                fi

                # Driver pods (RayJob submission pods)
                local driver_pods
                driver_pods=$(kubectl get pods -n $NAMESPACE -l ray.io/job-name="$job_name" --no-headers 2>/dev/null || true)
                if [[ -z "$driver_pods" ]]; then
                    print_status "WARN" "No driver pod yet for RayJob '$job_name'"
                else
                    while read -r line; do
                        [[ -z "$line" ]] && continue
                        local pod_name phase restarts age
                        pod_name=$(echo "$line" | awk '{print $1}')
                        phase=$(echo "$line" | awk '{print $3}')
                        restarts=$(echo "$line" | awk '{print $4}')
                        age=$(echo "$line" | awk '{print $5}')
                        if [[ "$phase" == "Running" ]]; then
                            print_status "PASS" "Driver pod '$pod_name' Running (restarts=$restarts age=$age)"
                        elif [[ "$phase" == "Completed" || "$phase" == "Succeeded" ]]; then
                            print_status "PASS" "Driver pod '$pod_name' Completed"
                        else
                            # Try to fetch waiting/terminated reason
                            local reason message
                            reason=$(kubectl get pod "$pod_name" -n $NAMESPACE -o jsonpath='{.status.containerStatuses[0].state.waiting.reason}' 2>/dev/null || true)
                            if [[ -z "$reason" ]]; then
                                reason=$(kubectl get pod "$pod_name" -n $NAMESPACE -o jsonpath='{.status.containerStatuses[0].state.terminated.reason}' 2>/dev/null || echo "Unknown")
                                message=$(kubectl get pod "$pod_name" -n $NAMESPACE -o jsonpath='{.status.containerStatuses[0].state.terminated.message}' 2>/dev/null || true)
                            else
                                message=$(kubectl get pod "$pod_name" -n $NAMESPACE -o jsonpath='{.status.containerStatuses[0].state.waiting.message}' 2>/dev/null || true)
                            fi
                            if [[ -n "$message" ]]; then
                                print_status "FAIL" "Driver pod '$pod_name' phase=$phase reason=$reason: ${message:0:120}"
                            else
                                print_status "FAIL" "Driver pod '$pod_name' phase=$phase reason=$reason"
                            fi
                        fi
                    done <<< "$driver_pods"
                fi
            }

            # Invoke diagnostics for the known RayJob
            check_ray_job "rayjob-recommendations-training"
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
        if $RAY_DIAG; then
            echo ""
            echo "🔎 Running extended Ray diagnostics (--ray-diagnostics)"
            bash "$SCRIPT_DIR/ray-diagnostics.sh" -n "$NAMESPACE" -j rayjob-recommendations-training || true
        fi
        echo ""
        echo "🚀 Next steps:"
        echo "   - Access MinIO Console: kubectl port-forward svc/minio 9001:9001 -n $NAMESPACE"
        echo "   - Access Spark UI: kubectl port-forward svc/spark-master 8080:8080 -n $NAMESPACE"
        echo "   - Access Flink UI: kubectl port-forward svc/flink-jobmanager 8081:8081 -n $NAMESPACE"
        echo "   - Submit jobs: ./submit-sample-jobs.sh"
        exit 0
    else
        print_status "FAIL" "$failed_checks validation checks failed. Please review the issues above."
        if $RAY_DIAG; then
            echo ""
            echo "🔎 Running extended Ray diagnostics (--ray-diagnostics) despite failures"
            bash "$SCRIPT_DIR/ray-diagnostics.sh" -n "$NAMESPACE" -j rayjob-recommendations-training || true
        fi
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