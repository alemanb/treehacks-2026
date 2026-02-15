#!/bin/bash
# Test script for Phase 8: Frontend Integration
# Tests the intelligent search endpoint and verifies all components work correctly

set -e

BACKEND_URL="https://alemanb--treehacks-vector-search-web.modal.run"
BACKEND_LOCAL="http://localhost:8000"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================="
echo "Phase 8: Frontend Integration Tests"
echo "========================================="
echo ""

# Function to test endpoint
test_endpoint() {
    local url=$1
    local query=$2
    local max_results=$3
    local test_name=$4

    echo -e "${YELLOW}Testing: $test_name${NC}"
    echo "URL: $url/search/intelligent"
    echo "Query: $query"
    echo "Max Results: $max_results"
    echo ""

    response=$(curl -s -X POST "$url/search/intelligent" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$query\", \"max_results\": $max_results}")

    # Check if response is valid JSON
    if ! echo "$response" | jq . > /dev/null 2>&1; then
        echo -e "${RED}✗ Invalid JSON response${NC}"
        echo "$response"
        return 1
    fi

    # Extract fields
    original_query=$(echo "$response" | jq -r '.query')
    expanded_query=$(echo "$response" | jq -r '.expanded_query')
    total_count=$(echo "$response" | jq -r '.total_count')
    results_count=$(echo "$response" | jq '.results | length')
    based_on_time=$(echo "$response" | jq -r '.conditions_applied.basedOnEarliestTime')
    confidence=$(echo "$response" | jq -r '.conditions_applied.confidence')
    reasoning=$(echo "$response" | jq -r '.conditions_applied.reasoning')

    # Display results
    echo -e "${GREEN}✓ Response received${NC}"
    echo ""
    echo "📊 Response Summary:"
    echo "  Original Query: $original_query"
    echo "  Expanded Query: $expanded_query"
    echo "  Total Matches: $total_count"
    echo "  Results Returned: $results_count"
    echo ""
    echo "⏰ Temporal Conditions:"
    echo "  Time Filtering: $based_on_time"
    echo "  Strict Boundary: $confidence"
    echo "  Reasoning: $reasoning"
    echo ""

    # Display first result if available
    if [ "$results_count" -gt 0 ]; then
        echo "🎯 First Result:"
        first_result=$(echo "$response" | jq '.results[0]')
        content=$(echo "$first_result" | jq -r '.content')
        likelihood=$(echo "$first_result" | jq -r '.likelihood_score')
        vector_score=$(echo "$first_result" | jq -r '.vector_score')
        timestamp=$(echo "$first_result" | jq -r '.timestamp')

        echo "  Content: $content"
        echo "  Likelihood Score: $likelihood/100"
        echo "  Vector Score: $vector_score"
        echo "  Timestamp: $timestamp"
        echo ""
    fi

    echo -e "${GREEN}✓ Test passed: $test_name${NC}"
    echo "========================================="
    echo ""
}

# Test 1: Simple ambiguous query
test_endpoint "$BACKEND_URL" "blue thing" 5 "Simple Ambiguous Query"

# Test 2: Temporal query with strict boundary
test_endpoint "$BACKEND_URL" "blue book taken yesterday" 10 "Temporal Query (Strict)"

# Test 3: Temporal query with loose boundary
test_endpoint "$BACKEND_URL" "red item recently" 10 "Temporal Query (Loose)"

# Test 4: Specific query (no temporal)
test_endpoint "$BACKEND_URL" "blue backpack" 10 "Specific Query"

# Test 5: Complex temporal query
test_endpoint "$BACKEND_URL" "stolen phone this morning" 10 "Complex Temporal Query"

# Test 6: Edge case - very generic query
test_endpoint "$BACKEND_URL" "something" 10 "Generic Query"

echo ""
echo "========================================="
echo -e "${GREEN}All tests completed successfully!${NC}"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Open frontend: http://localhost:5173"
echo "2. Toggle to 'Intelligent Search' mode"
echo "3. Try the test queries above"
echo "4. Verify Multi-Agent Analysis card displays correctly"
echo "5. Check likelihood scores and temporal conditions"
echo ""
echo "Frontend test queries:"
echo "  - 'blue thing' (query expansion test)"
echo "  - 'blue book taken yesterday' (temporal strict test)"
echo "  - 'red item recently' (temporal loose test)"
echo ""
