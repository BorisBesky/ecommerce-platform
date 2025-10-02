#!/bin/bash

# Deploy with Kustomize - select registry overlay
# Usage: ./deploy-with-kustomize.sh [local|ghcr] [apply|build|diff]

set -e

OVERLAY="${1:-local}"  # Default to local
ACTION="${2:-apply}"   # Default to apply

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_usage() {
    echo "Usage: $0 [overlay] [action]"
    echo ""
    echo "Overlays:"
    echo "  local   - Use local registry (localhost:5001) [default]"
    echo "  ghcr    - Use GitHub Container Registry (ghcr.io/borisbesky)"
    echo ""
    echo "Actions:"
    echo "  apply   - Apply the configuration to cluster [default]"
    echo "  build   - Just build and show the output (dry-run)"
    echo "  diff    - Show diff between current and new config"
    echo "  delete  - Delete resources"
    echo ""
    echo "Examples:"
    echo "  $0                    # Apply with local overlay"
    echo "  $0 local build        # Build and show local config"
    echo "  $0 ghcr apply         # Apply with GHCR overlay"
    echo "  $0 ghcr diff          # Show diff for GHCR config"
}

validate_overlay() {
    if [[ ! -d "overlays/${OVERLAY}" ]]; then
        echo -e "${RED}Error: Overlay '${OVERLAY}' not found${NC}"
        echo "Available overlays:"
        ls -d overlays/*/ 2>/dev/null | xargs -n 1 basename || echo "  (none found)"
        exit 1
    fi
}

check_prerequisites() {
    # Check if namespace exists
    if ! kubectl get namespace ecommerce-platform &>/dev/null; then
        echo -e "${YELLOW}Namespace 'ecommerce-platform' not found. Creating...${NC}"
        kubectl create namespace ecommerce-platform
    fi
    
    # Check if other required resources exist (MinIO, Nessie, etc.)
    if [[ "${ACTION}" == "apply" ]]; then
        if ! kubectl get configmap spark-apps -n ecommerce-platform &>/dev/null; then
            echo -e "${YELLOW}Warning: spark-apps ConfigMap not found${NC}"
            echo "You may need to create it before Spark deployments will work"
        fi
    fi
}

build_config() {
    echo -e "${BLUE}Building configuration with overlay: ${OVERLAY}${NC}"
    kubectl kustomize "overlays/${OVERLAY}"
}

apply_config() {
    echo -e "${GREEN}Applying configuration with overlay: ${OVERLAY}${NC}"
    echo ""
    kubectl apply -k "overlays/${OVERLAY}"
    echo ""
    echo -e "${GREEN}✓ Successfully applied configuration${NC}"
    echo ""
    echo "Check deployment status:"
    echo "  kubectl get pods -n ecommerce-platform -l app=spark"
    echo "  kubectl get pods -n ecommerce-platform -l app=flink"
}

diff_config() {
    echo -e "${BLUE}Showing diff for overlay: ${OVERLAY}${NC}"
    echo ""
    kubectl diff -k "overlays/${OVERLAY}" || true
}

delete_config() {
    echo -e "${YELLOW}Deleting resources with overlay: ${OVERLAY}${NC}"
    read -p "Are you sure? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        kubectl delete -k "overlays/${OVERLAY}"
        echo -e "${GREEN}✓ Resources deleted${NC}"
    else
        echo "Cancelled"
    fi
}

# Main script
case "$1" in
    -h|--help|help)
        print_usage
        exit 0
        ;;
esac

# Validate we're in the k8s directory
if [[ ! -d "overlays" ]] || [[ ! -d "base" ]]; then
    echo -e "${RED}Error: overlays/ and base/ directories not found${NC}"
    echo "Please run this script from the k8s directory"
    exit 1
fi

validate_overlay

case "${ACTION}" in
    apply)
        check_prerequisites
        apply_config
        ;;
    build|show)
        build_config
        ;;
    diff)
        diff_config
        ;;
    delete|remove)
        delete_config
        ;;
    *)
        echo -e "${RED}Error: Invalid action '${ACTION}'${NC}"
        echo ""
        print_usage
        exit 1
        ;;
esac
