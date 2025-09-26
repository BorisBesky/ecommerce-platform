#!/usr/bin/env bash
# Automated Ray Job / Cluster diagnostics
# Usage:
#   ./k8s/ray-diagnostics.sh                 # defaults (namespace ecommerce-platform, job rayjob-recommendations-training)
#   ./k8s/ray-diagnostics.sh -n other-ns -j myjob
#   RAY_JOB=myjob ./k8s/ray-diagnostics.sh
#
# Sections:
#  1. CR existence & quick status
#  2. RayCluster status & pod summary
#  3. Driver pod(s) deep dive
#  4. Worker/head pod deep dive (non-running)
#  5. ConfigMap / script mount validation
#  6. Scheduling & recent events (filtered)
#  7. Node resources & taints
#  8. Failure reason summary + hints
#
set -euo pipefail

NAMESPACE="${NAMESPACE:-ecommerce-platform}"
JOB_NAME="${RAY_JOB:-rayjob-recommendations-training}"
COLOR=${COLOR:-true}

while [[ $# -gt 0 ]]; do
  case $1 in
    -n|--namespace) NAMESPACE=$2; shift 2;;
    -j|--job) JOB_NAME=$2; shift 2;;
    -q|--no-color) COLOR=false; shift;;
    -h|--help)
      echo "Usage: $0 [-n namespace] [-j jobName] [--no-color]"; exit 0;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

if $COLOR; then
  RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; CYAN=''; NC=''
fi

hr() { echo -e "${CYAN}--------------------------------------------------------------------------------${NC}"; }
section() { echo -e "\n${CYAN}### $1${NC}"; }
status_line() { local s=$1 msg=$2; case $s in PASS) echo -e "${GREEN}[PASS]${NC} $msg";; WARN) echo -e "${YELLOW}[WARN]${NC} $msg";; FAIL) echo -e "${RED}[FAIL]${NC} $msg";; *) echo "[INFO] $msg";; esac; }

cmd() { echo "+ $*"; eval "$*"; }

echo -e "${CYAN}Ray Diagnostics for job '${JOB_NAME}' in namespace '${NAMESPACE}'${NC}"; hr

KUBECTL_OK=true
if ! command -v kubectl >/dev/null 2>&1; then
  status_line FAIL "kubectl not found"; exit 2
fi

if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
  status_line FAIL "Namespace '$NAMESPACE' not found"; exit 3
fi

section "1. RayJob Status"
if ! kubectl get rayjob "$JOB_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
  status_line FAIL "RayJob '$JOB_NAME' not found"; exit 4
fi

JOB_JSON=$(kubectl get rayjob "$JOB_NAME" -n "$NAMESPACE" -o json)
JOB_STATE=$(echo "$JOB_JSON" | jq -r '.status.jobStatus // "Unknown"')
RC_NAME=$(echo "$JOB_JSON" | jq -r '.status.rayClusterName // ""')
JOB_MSG=$(echo "$JOB_JSON" | jq -r '.status.message // empty')
status_line INFO "JobStatus: $JOB_STATE  RayCluster: ${RC_NAME:-<pending>}"
[[ -n "$JOB_MSG" ]] && status_line INFO "Controller message: $JOB_MSG"

section "2. RayCluster Status"
SHUTDOWN_AFTER_FINISH=$(echo "$JOB_JSON" | jq -r '.spec.shutdownAfterJobFinishes // false')
if [[ -n "$RC_NAME" ]] && kubectl get raycluster "$RC_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
  RC_JSON=$(kubectl get raycluster "$RC_NAME" -n "$NAMESPACE" -o json)
  RC_STATE=$(echo "$RC_JSON" | jq -r '.status.state // "Unknown"')
  DASH_URL=$(echo "$RC_JSON" | jq -r '.status.dashboardURL // empty')
  status_line INFO "RayCluster state: $RC_STATE"
  [[ -n "$DASH_URL" && "$DASH_URL" != "null" ]] && status_line INFO "Dashboard: $DASH_URL"
  echo "Cluster Pods:"; kubectl get pods -n "$NAMESPACE" -l ray.io/cluster="$RC_NAME" -o wide || true
else
  if [[ "$JOB_STATE" == "SUCCEEDED" && "$SHUTDOWN_AFTER_FINISH" == "true" ]]; then
    status_line PASS "RayCluster already cleaned up after successful job (shutdownAfterJobFinishes=true)"
  elif [[ "$JOB_STATE" == "FAILED" && "$SHUTDOWN_AFTER_FINISH" == "true" ]]; then
    status_line WARN "RayCluster cleaned up despite failure (check controller settings)"
  else
    status_line WARN "No RayCluster resource present (still provisioning or already deleted)"
  fi
fi

section "3. Driver Pod(s)"
DRIVER_PODS=$(kubectl get pods -n "$NAMESPACE" -l ray.io/job-name="$JOB_NAME" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true)
if [[ -z "$DRIVER_PODS" ]]; then
  status_line WARN "No driver pods created yet"
else
  kubectl get pods -n "$NAMESPACE" -l ray.io/job-name="$JOB_NAME" -o wide
  echo ""
  for p in $DRIVER_PODS; do
    echo "--- Driver Pod: $p (container states)";
    kubectl get pod "$p" -n "$NAMESPACE" -o json | jq '.status.containerStatuses[] | {name, state, lastState, restartCount}' || true
    echo "Logs (last 60 lines):"; kubectl logs "$p" -n "$NAMESPACE" --tail=60 || true
  done
fi

section "4. Non-running Cluster Pods (Head/Workers)"
if [[ -n "${RC_NAME}" ]] && kubectl get raycluster "$RC_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
  POD_LIST=$(kubectl get pods -n "$NAMESPACE" -l ray.io/cluster="$RC_NAME" --no-headers 2>/dev/null || true)
  if [[ -z "$POD_LIST" ]]; then
    status_line WARN "No cluster pods found (may be terminating)"
  else
    BAD_PODS=$(echo "$POD_LIST" | awk '$3!="Running"') || true
    if [[ -z "$BAD_PODS" ]]; then
      COUNT=$(echo "$POD_LIST" | wc -l | tr -d ' ')
      status_line PASS "All cluster pods Running ($COUNT)"
    else
      echo "$BAD_PODS" | while read -r line; do
        [[ -z "$line" ]] && continue
        pod=$(echo "$line" | awk '{print $1}') phase=$(echo "$line" | awk '{print $3}')
        status_line WARN "Pod $pod phase=$phase"
        echo "  Container states:"; kubectl get pod "$pod" -n "$NAMESPACE" -o json | jq '.status.containerStatuses[] | {name,state,lastState,restartCount}' || true
        echo "  Recent Events:"; kubectl describe pod "$pod" -n "$NAMESPACE" | sed -n '/Events:/,$p' | tail -n +2 | head -n 15 || true
      done
    fi
  fi
else
  if [[ "$JOB_STATE" == "SUCCEEDED" && "$SHUTDOWN_AFTER_FINISH" == "true" ]]; then
    status_line INFO "Cluster pods intentionally gone after success"
  fi
fi

section "5. Training Script ConfigMap"
if kubectl get configmap ray-training-script -n "$NAMESPACE" >/dev/null 2>&1; then
  CM_KEYS=$(kubectl get configmap ray-training-script -n "$NAMESPACE" -o jsonpath='{.data}' | jq 'keys')
  if echo "$CM_KEYS" | grep -q 'train_recommendation_model_k8s.py'; then
    status_line PASS "ConfigMap ray-training-script present with training script"
  else
    status_line FAIL "ConfigMap exists but training script key missing. Keys: $CM_KEYS"
  fi
else
  status_line FAIL "ConfigMap ray-training-script not found"
fi

section "6. Recent Scheduling / Pod Events (filtered)"
# Filter only last 60 relevant events for ray items
kubectl get events -n "$NAMESPACE" --sort-by=.lastTimestamp \
  | egrep 'rayjob|raycluster|FailedScheduling|BackOff|Image|Pulled|Created|Killing' | tail -n 60 || true

section "7. Node Resources & Taints"
# Node summary
kubectl get nodes -o wide || true
echo "Allocatable:"; kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, allocatable: .status.allocatable}' || true
# Taints
echo "Node Taints:"; kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, taints: (.spec.taints // [])}' || true
# Usage (optional metrics)
if kubectl top nodes >/dev/null 2>&1; then
  echo "kubectl top nodes:"; kubectl top nodes || true
else
  status_line WARN "metrics-server not available for 'kubectl top'"
fi

section "8. Failure Reason Summary"
FAIL_REASONS=()
# Collect from driver pods
if [[ -n "$DRIVER_PODS" ]]; then
  for p in $DRIVER_PODS; do
    r=$(kubectl get pod "$p" -n "$NAMESPACE" -o jsonpath='{.status.containerStatuses[0].state.waiting.reason}' 2>/dev/null || true)
    [[ -z "$r" ]] && r=$(kubectl get pod "$p" -n "$NAMESPACE" -o jsonpath='{.status.containerStatuses[0].state.terminated.reason}' 2>/dev/null || true)
    [[ -n "$r" ]] && FAIL_REASONS+=("$r")
  done
fi
# Cluster bad pods
if [[ -n "${RC_NAME}" ]]; then
  for p in $(kubectl get pods -n "$NAMESPACE" -l ray.io/cluster="$RC_NAME" --no-headers 2>/dev/null | awk '$3!="Running" {print $1}'); do
    r=$(kubectl get pod "$p" -n "$NAMESPACE" -o jsonpath='{.status.containerStatuses[0].state.waiting.reason}' 2>/dev/null || true)
    [[ -z "$r" ]] && r=$(kubectl get pod "$p" -n "$NAMESPACE" -o jsonpath='{.status.containerStatuses[0].state.terminated.reason}' 2>/dev/null || true)
    [[ -n "$r" ]] && FAIL_REASONS+=("$r")
  done
fi

if [[ ${#FAIL_REASONS[@]} -eq 0 ]]; then
  status_line INFO "No explicit failure reasons collected (pods may be Pending only)."
else
  UNIQUE=$(printf '%s\n' "${FAIL_REASONS[@]}" | sort -u)
  echo "Reasons: $UNIQUE"
  echo "Hints:";
  echo "$UNIQUE" | while read -r reason; do
    case $reason in
      ImagePullBackOff|ErrImagePull)
        echo " - $reason: Check image name/tag, registry auth, network access.";;
      CrashLoopBackOff)
        echo " - CrashLoopBackOff: Inspect container logs; likely script error or missing dependency.";;
      OOMKilled)
        echo " - OOMKilled: Reduce memory requests/limits or increase node memory.";;
      FailedScheduling)
        echo " - FailedScheduling: Insufficient resources or taints; adjust requests or add tolerations.";;
      CreateContainerConfigError)
        echo " - CreateContainerConfigError: Often missing/misnamed ConfigMap or volume mount path.";;
      *)
        echo " - $reason: Review describe/logs for more detail.";;
    esac
  done
fi

EXIT_CODE=0
case $JOB_STATE in
  FAILED) EXIT_CODE=20;;
  SUCCEEDED) EXIT_CODE=0;;
  *) :;;
esac

exit $EXIT_CODE
