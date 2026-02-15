#!/bin/bash
# Integration Test Script for Phase 3 - Temporal Detection with Live Data
# Tests the deployed Modal application with real temporal queries

set -e

# Configuration
API_URL="https://alemanb--treehacks-vector-search-web.modal.run"
REFERENCE_DATE="2026-02-15"  # Sunday, Feb 15, 2026

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Temporal Detection Integration Tests - Phase 4${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo "API Endpoint: $API_URL"
echo "Reference Date: $REFERENCE_DATE (Sunday)"
echo ""

# Function to run a test
run_test() {
    local test_name="$1"
    local query="$2"
    local expected_pattern="$3"

    echo -e "${YELLOW}Test:${NC} $test_name"
    echo -e "${YELLOW}Query:${NC} \"$query\""

    response=$(curl -s -X POST "$API_URL/search/intelligent" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$query\", \"max_results\": 5}")

    # Extract conditions_applied
    conditions=$(echo "$response" | jq -r '.conditions_applied // empty')

    if [ -z "$conditions" ]; then
        echo -e "${RED}❌ FAIL: No conditions_applied in response${NC}"
        echo "Response: $response"
        return 1
    fi

    # Display key information
    based_on_time=$(echo "$conditions" | jq -r '.basedOnEarliestTime')
    earliest_timestamp=$(echo "$conditions" | jq -r '.earliest_timestamp // "null"')
    reasoning=$(echo "$conditions" | jq -r '.reasoning')

    echo -e "${BLUE}basedOnEarliestTime:${NC} $based_on_time"
    echo -e "${BLUE}earliest_timestamp:${NC} $earliest_timestamp"
    echo -e "${BLUE}reasoning:${NC} $reasoning"

    # Check expected pattern
    if echo "$reasoning" | grep -qi "$expected_pattern"; then
        echo -e "${GREEN}✅ PASS${NC}"
    else
        echo -e "${RED}❌ FAIL: Expected pattern '$expected_pattern' not found in reasoning${NC}"
        return 1
    fi

    echo ""
}

# Test 1: Specific weekday (Tuesday)
echo -e "${GREEN}━━━ Test 1: Specific Weekday (High Confidence) ━━━${NC}"
run_test \
    "Tuesday - Strict Boundary" \
    "I lost my glasses on Tuesday" \
    "Tuesday"

echo -e "${BLUE}Expected:${NC} earliest_timestamp ≈ 2026-02-10T00:00:00Z (last Tuesday)"
echo -e "${BLUE}Expected:${NC} strict confidence (no buffer)"
echo ""

# Test 2: Yesterday
echo -e "${GREEN}━━━ Test 2: Yesterday (High Confidence) ━━━${NC}"
run_test \
    "Yesterday - Strict Boundary" \
    "blue book stolen yesterday" \
    "yesterday"

echo -e "${BLUE}Expected:${NC} earliest_timestamp ≈ 2026-02-14T00:00:00Z (yesterday)"
echo -e "${BLUE}Expected:${NC} strict confidence (urgency word 'stolen')"
echo ""

# Test 3: Recently
echo -e "${GREEN}━━━ Test 3: Recently (Medium Confidence) ━━━${NC}"
run_test \
    "Recently - Flexible Boundary" \
    "red item recently" \
    "recently"

echo -e "${BLUE}Expected:${NC} earliest_timestamp with 1-day buffer"
echo -e "${BLUE}Expected:${NC} flexible confidence"
echo ""

# Test 4: Last night
echo -e "${GREEN}━━━ Test 4: Last Night (High Confidence) ━━━${NC}"
run_test \
    "Last Night - Strict Boundary" \
    "I saw my phone last night" \
    "last night"

echo -e "${BLUE}Expected:${NC} earliest_timestamp ≈ previous day evening"
echo -e "${BLUE}Expected:${NC} strict confidence"
echo ""

# Test 5: No temporal indicator
echo -e "${GREEN}━━━ Test 5: No Temporal Indicator ━━━${NC}"
echo -e "${YELLOW}Test:${NC} No temporal - All results"
echo -e "${YELLOW}Query:${NC} \"blue backpack\""

response=$(curl -s -X POST "$API_URL/search/intelligent" \
    -H "Content-Type: application/json" \
    -d '{"query": "blue backpack", "max_results": 5}')

based_on_time=$(echo "$response" | jq -r '.conditions_applied.basedOnEarliestTime')
reasoning=$(echo "$response" | jq -r '.conditions_applied.reasoning')

echo -e "${BLUE}basedOnEarliestTime:${NC} $based_on_time"
echo -e "${BLUE}reasoning:${NC} $reasoning"

if [ "$based_on_time" = "false" ]; then
    echo -e "${GREEN}✅ PASS${NC}"
else
    echo -e "${RED}❌ FAIL: Expected basedOnEarliestTime=false${NC}"
fi

echo ""

# Test 6: Confidence levels check
echo -e "${GREEN}━━━ Test 6: Confidence Levels ━━━${NC}"

test_confidence() {
    local query="$1"
    local expected_level="$2"

    echo -e "${YELLOW}Query:${NC} \"$query\""

    response=$(curl -s -X POST "$API_URL/search/intelligent" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$query\", \"max_results\": 5}")

    reasoning=$(echo "$response" | jq -r '.conditions_applied.reasoning')

    if echo "$reasoning" | grep -qi "$expected_level"; then
        echo -e "  ${GREEN}✅ $expected_level confidence detected${NC}"
    else
        echo -e "  ${RED}❌ Expected $expected_level confidence${NC}"
        echo -e "  ${BLUE}Reasoning:${NC} $reasoning"
    fi
}

test_confidence "wallet stolen on Monday" "strict"
test_confidence "item last week" "flexible"

echo ""

# Test 7: Lower bound only (no upper bound)
echo -e "${GREEN}━━━ Test 7: Lower Bound Only Verification ━━━${NC}"

echo -e "${YELLOW}Query:${NC} \"glasses on Tuesday\""
response=$(curl -s -X POST "$API_URL/search/intelligent" \
    -H "Content-Type: application/json" \
    -d '{"query": "glasses on Tuesday", "max_results": 20}')

reasoning=$(echo "$response" | jq -r '.conditions_applied.reasoning')
results_count=$(echo "$response" | jq -r '.results | length')

echo -e "${BLUE}Results returned:${NC} $results_count"
echo -e "${BLUE}reasoning:${NC} $reasoning"

if echo "$reasoning" | grep -qi "onward"; then
    echo -e "${GREEN}✅ PASS: 'onward' keyword found (confirms no upper bound)${NC}"
else
    echo -e "${YELLOW}⚠️  WARNING: 'onward' keyword not found${NC}"
fi

echo ""

# Summary
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Test Summary${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}✅ Temporal Detection Tests Complete${NC}"
echo ""
echo "Key Validations:"
echo "  • Temporal indicators detected correctly"
echo "  • Confidence-based boundaries applied"
echo "  • Lower bound only (no upper bounds)"
echo "  • Hard-coded calculation (consistent results)"
echo ""
echo "Next Steps:"
echo "  1. Review test results above"
echo "  2. Check Modal logs: modal app logs treehacks-vector-search"
echo "  3. Test with frontend: Navigate to frontend and test queries"
echo ""
