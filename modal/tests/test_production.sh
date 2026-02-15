#!/bin/bash
# Production endpoint testing script
# Usage: ./test_production.sh [production_url]

PROD_URL="${1:-https://alemanb--treehacks-vector-search-web.modal.run}"

echo "🧪 Testing Production Endpoint"
echo "=============================="
echo "Production URL: $PROD_URL"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Test 1: Health Check
echo "Test 1: Production Health Check"
echo "--------------------------------"
response=$(curl -s "$PROD_URL/health" -w "\n%{http_code}")
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
    echo -e "${GREEN}✅ PASS${NC} - Health endpoint responding (HTTP $http_code)"
    echo "Response: $body"
else
    echo -e "${RED}❌ FAIL${NC} - Health endpoint failed (HTTP $http_code)"
    echo "Response: $body"
fi
echo ""

# Test 2: Intelligent Search - Simple Query
echo "Test 2: Intelligent Search - Simple Query"
echo "------------------------------------------"
echo "Query: 'blue thing'"
response=$(curl -s -X POST "$PROD_URL/search/intelligent" \
    -H "Content-Type: application/json" \
    -d '{"query": "blue thing", "max_results": 5}' \
    -w "\n%{http_code}")
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
    echo -e "${GREEN}✅ PASS${NC} - Intelligent search working (HTTP $http_code)"
    echo "Response preview:"
    echo "$body" | python3 -m json.tool 2>/dev/null | head -30
else
    echo -e "${RED}❌ FAIL${NC} - Intelligent search failed (HTTP $http_code)"
    echo "Response: $body"
fi
echo ""

# Test 3: Performance Check
echo "Test 3: Performance Check"
echo "-------------------------"
echo "Measuring response time for intelligent search..."

start_time=$(date +%s%N)
response=$(curl -s -X POST "$PROD_URL/search/intelligent" \
    -H "Content-Type: application/json" \
    -d '{"query": "red bag", "max_results": 10}' \
    -w "\n%{http_code}")
end_time=$(date +%s%N)

http_code=$(echo "$response" | tail -n1)
duration=$(( (end_time - start_time) / 1000000 ))  # Convert to milliseconds

if [ "$http_code" = "200" ]; then
    echo -e "${GREEN}✅ PASS${NC} - Response received (HTTP $http_code)"
    echo "Response time: ${duration}ms"
    
    if [ "$duration" -lt 10000 ]; then
        echo -e "${GREEN}✅ PASS${NC} - Response time within acceptable range (<10s)"
    else
        echo -e "${YELLOW}⚠️  WARN${NC} - Response time high (>10s). Expected: 3-5s"
    fi
else
    echo -e "${RED}❌ FAIL${NC} - Request failed (HTTP $http_code)"
fi
echo ""

# Test 4: Error Handling
echo "Test 4: Error Handling - Empty Query"
echo "-------------------------------------"
response=$(curl -s -X POST "$PROD_URL/search/intelligent" \
    -H "Content-Type: application/json" \
    -d '{"query": "", "max_results": 10}' \
    -w "\n%{http_code}")
http_code=$(echo "$response" | tail -n1)

if [ "$http_code" = "400" ]; then
    echo -e "${GREEN}✅ PASS${NC} - Error handling working (HTTP $http_code)"
else
    echo -e "${YELLOW}⚠️  WARN${NC} - Unexpected response (HTTP $http_code)"
fi
echo ""

echo "=============================="
echo "✅ Production Testing Complete"
echo "=============================="
echo ""
echo "📊 Next Steps:"
echo "1. Monitor logs: modal app logs treehacks-vector-search"
echo "2. Check metrics in Modal dashboard"
echo "3. Set up cost tracking in OpenAI dashboard"
echo "4. Configure frontend to use production URL"
