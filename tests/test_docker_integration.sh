#!/bin/bash

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Configuration
HEALTH_CHECK_URL="http://localhost/health"
PATIENTS_URL="http://localhost/api/v1/patients"
FRONTEND_URL="http://localhost/"
READINESS_URL="http://localhost/api/v1/health/ready"
MAX_WAIT_SECONDS=60
POLL_INTERVAL=5

# Cleanup function
cleanup() {
    local exit_code=$?

    echo ""
    echo "=== Cleaning up Docker stack ==="

    if docker compose down 2>/dev/null; then
        echo "Docker stack stopped successfully"
    else
        echo "Warning: Failed to stop Docker stack"
    fi

    exit $exit_code
}

# Set trap to ensure cleanup always runs
trap cleanup EXIT

# Function to wait for service to be healthy
wait_for_health() {
    local url=$1
    local service_name=$2
    local elapsed=0

    echo "Waiting for $service_name to be healthy..."

    while [ $elapsed -lt $MAX_WAIT_SECONDS ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ $service_name is healthy${NC}"
            return 0
        fi

        sleep $POLL_INTERVAL
        elapsed=$((elapsed + POLL_INTERVAL))
        echo "  Still waiting... ($elapsed/${MAX_WAIT_SECONDS}s)"
    done

    echo -e "${RED}✗ $service_name failed to become healthy within ${MAX_WAIT_SECONDS}s${NC}"
    echo ""
    echo "=== Docker Compose Logs ==="
    docker compose logs
    echo "=============================="
    return 1
}

# Main test execution
main() {
    cd "$PROJECT_ROOT"

    echo "=========================================="
    echo "Docker Integration Test Suite"
    echo "=========================================="
    echo ""

    # Build the stack
    echo "=== Building Docker stack ==="
    if ! docker compose build; then
        echo -e "${RED}✗ Docker build failed${NC}"
        return 1
    fi
    echo -e "${GREEN}✓ Docker build successful${NC}"
    echo ""

    # Start the stack
    echo "=== Starting Docker stack ==="
    if ! docker compose up -d; then
        echo -e "${RED}✗ Failed to start Docker stack${NC}"
        return 1
    fi
    echo -e "${GREEN}✓ Docker stack started${NC}"
    echo ""

    # Wait for services to be healthy
    if ! wait_for_health "$HEALTH_CHECK_URL" "Health endpoint"; then
        return 1
    fi
    echo ""

    # Test 1: Health endpoint returns "alive"
    echo "=== Test 1: Health Endpoint ==="
    HEALTH_RESPONSE=$(curl -sf "$HEALTH_CHECK_URL" 2>/dev/null || echo "")
    if echo "$HEALTH_RESPONSE" | grep -q "alive"; then
        echo -e "${GREEN}✓ Health endpoint returns 'alive'${NC}"
    else
        echo -e "${RED}✗ Health endpoint test failed${NC}"
        echo "  Response: $HEALTH_RESPONSE"
        return 1
    fi
    echo ""

    # Test 2: Patients list contains "P001"
    echo "=== Test 2: Patients List ==="
    PATIENTS_RESPONSE=$(curl -sf "$PATIENTS_URL" 2>/dev/null || echo "")
    if echo "$PATIENTS_RESPONSE" | grep -q "P001"; then
        echo -e "${GREEN}✓ Patients list contains 'P001'${NC}"
    else
        echo -e "${RED}✗ Patients list test failed${NC}"
        echo "  Response: $PATIENTS_RESPONSE"
        return 1
    fi
    echo ""

    # Test 3: Frontend returns HTTP 200
    echo "=== Test 3: Frontend Health ==="
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}✓ Frontend returns HTTP 200${NC}"
    else
        echo -e "${RED}✗ Frontend returned HTTP $HTTP_CODE (expected 200)${NC}"
        return 1
    fi
    echo ""

    # Test 4: Readiness check (warn-only if not ready, since no LLM key)
    echo "=== Test 4: Readiness Check (Warn-only) ==="
    READINESS_RESPONSE=$(curl -sf "$READINESS_URL" 2>/dev/null || echo "")
    if echo "$READINESS_RESPONSE" | grep -q "ready"; then
        echo -e "${GREEN}✓ System is ready${NC}"
    else
        echo -e "${YELLOW}⚠ System not fully ready (expected without LLM key)${NC}"
        echo "  Response: $READINESS_RESPONSE"
    fi
    echo ""

    # All tests passed
    echo "=========================================="
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo "=========================================="
    return 0
}

# Run main function
main
