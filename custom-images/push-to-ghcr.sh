#!/bin/bash

# Script to push local images to GHCR
# Usage: ./push-to-ghcr.sh [github-username]

set -e

GITHUB_USERNAME="${1:-BorisBesky}"  # Default to BorisBesky if not provided

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Registries
LOCAL_REGISTRY="localhost:5001"
GHCR_REGISTRY="ghcr.io/${GITHUB_USERNAME}"

# Image names
FLINK_IMAGE="custom-flink:latest"
SPARK_IMAGE="custom-spark:latest"

print_usage() {
    echo "Usage: $0 [github-username]"
    echo ""
    echo "This script will:"
    echo "  1. Tag local images for GHCR"
    echo "  2. Push images to GHCR"
    echo ""
    echo "Examples:"
    echo "  $0                    # Push to ghcr.io/BorisBesky"
    echo "  $0 YourUsername       # Push to ghcr.io/YourUsername"
    echo ""
    echo "Note: You need to be logged in to GHCR first:"
    echo "  echo \$GITHUB_TOKEN | docker login ghcr.io -u ${GITHUB_USERNAME} --password-stdin"
}

check_docker_login() {
    echo -e "${BLUE}Checking GHCR login status...${NC}"
    if ! docker pull ${GHCR_REGISTRY}/custom-flink:latest &>/dev/null && ! grep -q "ghcr.io" ~/.docker/config.json 2>/dev/null; then
        echo -e "${YELLOW}Warning: You may not be logged in to GHCR${NC}"
        echo "To login, run:"
        echo "  echo \$GITHUB_TOKEN | docker login ghcr.io -u ${GITHUB_USERNAME} --password-stdin"
        echo ""
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

check_local_images() {
    echo -e "${BLUE}Checking local images...${NC}"
    
    if ! docker image inspect ${LOCAL_REGISTRY}/${FLINK_IMAGE} &>/dev/null; then
        echo -e "${RED}Error: Local image ${LOCAL_REGISTRY}/${FLINK_IMAGE} not found${NC}"
        echo "Please build the image first"
        exit 1
    fi
    
    if ! docker image inspect ${LOCAL_REGISTRY}/${SPARK_IMAGE} &>/dev/null; then
        echo -e "${RED}Error: Local image ${LOCAL_REGISTRY}/${SPARK_IMAGE} not found${NC}"
        echo "Please build the image first"
        exit 1
    fi
    
    echo -e "${GREEN}✓ Local images found${NC}"
}

tag_and_push() {
    local image_name="$1"
    
    echo ""
    echo -e "${BLUE}Processing ${image_name}...${NC}"
    
    # Tag for GHCR
    echo "  Tagging ${LOCAL_REGISTRY}/${image_name} -> ${GHCR_REGISTRY}/${image_name}"
    docker tag ${LOCAL_REGISTRY}/${image_name} ${GHCR_REGISTRY}/${image_name}
    
    # Push to GHCR
    echo "  Pushing ${GHCR_REGISTRY}/${image_name}..."
    docker push ${GHCR_REGISTRY}/${image_name}
    
    echo -e "${GREEN}  ✓ Successfully pushed ${image_name}${NC}"
}

# Main script
case "$1" in
    -h|--help|help)
        print_usage
        exit 0
        ;;
esac

echo -e "${GREEN}=== Pushing images to GHCR ===${NC}"
echo "Target registry: ${GHCR_REGISTRY}"
echo ""

check_docker_login
check_local_images

tag_and_push "${FLINK_IMAGE}"
tag_and_push "${SPARK_IMAGE}"

echo ""
echo -e "${GREEN}=== Successfully pushed all images to GHCR ===${NC}"
echo ""
echo "Images available at:"
echo "  ${GHCR_REGISTRY}/${FLINK_IMAGE}"
echo "  ${GHCR_REGISTRY}/${SPARK_IMAGE}"
echo ""
echo "To switch your k8s deployments to use GHCR, run:"
echo "  ./switch-registry.sh ghcr ${GITHUB_USERNAME}"
