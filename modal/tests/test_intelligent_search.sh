#!/bin/bash
# Test script for intelligent search endpoint
# Usage: ./test_intelligent_search.sh [base_url]

BASE_URL="${1:-http://localhost:8000}"

echo "🧪 Testing Intelligent Search Endpoint"
echo "======================================"
echo "Base URL: $BASE_URL"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Health Check
echo "Test 1: Health Check"
echo "--------------------"
response=$(curl -s "$BASE_URL/health")
if echo "$response" | grep -q '"status":"ok"'; then
    echo -e "${GREEN}✅ PASS${NC} - Health endpoint working"
else
    echo -e "${RED}❌ FAIL${NC} - Health endpoint not responding"
    echo "Response: $response"
fi
echo ""

# Test 2: Simple Query Expansion
echo "Test 2: Simple Query Expansion"
echo "-------------------------------"
echo "Query: 'blue thing'"
response=$(curl -s -X POST "$BASE_URL/search/intelligent" \
    -H "Content-Type: application/json" \
    -d '{"query": "blue thing", "max_results": 5}')

if echo "$response" | grep -q "expanded_query"; then
    echo -e "${GREEN}✅ PASS${NC} - Query expansion working"
    echo "Response preview:"
    echo "$response" | python3 -m json.tool 2>/dev/null | head -20
else
    echo -e "${RED}❌ FAIL${NC} - Query expansion failed"
    echo "Response: $response"
fi
echo ""

# Test 3: Temporal Query (Strict Boundary)
echo "Test 3: Temporal Query - Strict Boundary"
echo "-----------------------------------------"
echo "Query: 'blue book taken yesterday'"
response=$(curl -s -X POST "$BASE_URL/search/intelligent" \
    -H "Content-Type: application/json" \
    -d '{"query": "blue book taken yesterday", "max_results": 10}')

if echo "$response" | grep -q "basedOnEarliestTime"; then
    echo -e "${GREEN}✅ PASS${NC} - Temporal detection working"
    # Check if temporal filtering is enabled
    if echo "$response" | grep -q '"basedOnEarliestTime":true'; then
        echo -e "${GREEN}✅ PASS${NC} - Temporal filtering enabled"
    else
        echo -e "${YELLOW}⚠️  WARN${NC} - Temporal filtering not enabled"
    fi
    echo "Conditions:"
    echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(json.dumps(data.get('conditions_applied', {}), indent=2))" 2>/dev/null
else
    echo -e "${RED}❌ FAIL${NC} - Temporal detection failed"
    echo "Response: $response"
fi
echo ""

# Test 4: Temporal Query (Loose Boundary)
echo "Test 4: Temporal Query - Loose Boundary"
echo "----------------------------------------"
echo "Query: 'blue thing recently'"
response=$(curl -s -X POST "$BASE_URL/search/intelligent" \
    -H "Content-Type: application/json" \
    -d '{"query": "blue thing recently", "max_results": 10}')

if echo "$response" | grep -q "time_window_minutes"; then
    echo -e "${GREEN}✅ PASS${NC} - Time window detection working"
    echo "Conditions:"
    echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(json.dumps(data.get('conditions_applied', {}), indent=2))" 2>/dev/null
else
    echo -e "${YELLOW}⚠️  WARN${NC} - Time window detection may not be working"
fi
echo ""

# Test 5: Non-Temporal Query
echo "Test 5: Non-Temporal Query"
echo "---------------------------"
echo "Query: 'red bag'"
response=$(curl -s -X POST "$BASE_URL/search/intelligent" \
    -H "Content-Type: application/json" \
    -d '{"query": "red bag", "max_results": 10}')

if echo "$response" | grep -q '"basedOnEarliestTime":false'; then
    echo -e "${GREEN}✅ PASS${NC} - Non-temporal query handled correctly"
else
    echo -e "${YELLOW}⚠️  WARN${NC} - Unexpected temporal filtering"
fi
echo ""

# Test 6: Complex Query
echo "Test 6: Complex Query"
echo "---------------------"
echo "Query: 'stolen blue backpack last night'"
response=$(curl -s -X POST "$BASE_URL/search/intelligent" \
    -H "Content-Type: application/json" \
    -d '{"query": "stolen blue backpack last night", "max_results": 10}')

if echo "$response" | grep -q "expanded_query"; then
    echo -e "${GREEN}✅ PASS${NC} - Complex query processing working"
    echo "Expanded query:"
    echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('expanded_query', 'N/A'))" 2>/dev/null
else
    echo -e "${RED}❌ FAIL${NC} - Complex query failed"
fi
echo ""

# Test 7: Invalid Query (Empty)
echo "Test 7: Invalid Query - Empty String"
echo "-------------------------------------"
response=$(curl -s -X POST "$BASE_URL/search/intelligent" \
    -H "Content-Type: application/json" \
    -d '{"query": "", "max_results": 10}')

if echo "$response" | grep -q "must be a non-empty string"; then
    echo -e "${GREEN}✅ PASS${NC} - Empty query validation working"
else
    echo -e "${RED}❌ FAIL${NC} - Empty query validation failed"
fi
echo ""

# Test 8: Invalid max_results
echo "Test 8: Invalid max_results (>50)"
echo "----------------------------------"
response=$(curl -s -X POST "$BASE_URL/search/intelligent" \
    -H "Content-Type: application/json" \
    -d '{"query": "test", "max_results": 100}')

if echo "$response" | grep -q "detail"; then
    echo -e "${GREEN}✅ PASS${NC} - max_results validation working"
else
    echo -e "${RED}❌ FAIL${NC} - max_results validation failed"
fi
echo ""

echo "======================================"
echo "✅ Testing Complete"
echo "======================================"
