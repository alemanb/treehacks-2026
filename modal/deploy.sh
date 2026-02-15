#!/bin/bash
# Production deployment script for intelligent search system
# Usage: ./deploy.sh

set -e  # Exit on error

echo "🚀 TreeHacks Vector Search - Production Deployment"
echo "=================================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check prerequisites
echo "📋 Pre-Deployment Checks"
echo "------------------------"

# Check if in modal directory
if [ ! -f "main.py" ]; then
    echo -e "${RED}❌ Error: main.py not found. Run from modal/ directory.${NC}"
    exit 1
fi
echo -e "${GREEN}✅${NC} main.py found"

# Check Modal CLI
if ! command -v modal &> /dev/null; then
    echo -e "${RED}❌ Error: Modal CLI not installed${NC}"
    echo "Install: pip install modal"
    exit 1
fi
echo -e "${GREEN}✅${NC} Modal CLI installed"

# Check Modal authentication
if ! modal token list &> /dev/null; then
    echo -e "${RED}❌ Error: Not authenticated with Modal${NC}"
    echo "Run: modal token new"
    exit 1
fi
echo -e "${GREEN}✅${NC} Modal authenticated"

# Check secrets
echo ""
echo "🔐 Checking Modal Secrets"
echo "-------------------------"

secrets_output=$(modal secret list 2>&1)

if echo "$secrets_output" | grep -q "jina-secret"; then
    echo -e "${GREEN}✅${NC} jina-secret exists"
else
    echo -e "${RED}❌${NC} jina-secret not found"
    echo "Create with: modal secret create jina-secret JINA_API_KEY=\$JINA_API_KEY"
    exit 1
fi

if echo "$secrets_output" | grep -q "elastic-secret"; then
    echo -e "${GREEN}✅${NC} elastic-secret exists"
else
    echo -e "${RED}❌${NC} elastic-secret not found"
    echo "Create with: modal secret create elastic-secret ES_API_KEY=\$ES_API_KEY"
    exit 1
fi

if echo "$secrets_output" | grep -q "openai-secret"; then
    echo -e "${GREEN}✅${NC} openai-secret exists"
else
    echo -e "${YELLOW}⚠️${NC}  openai-secret not found"
    echo "Intelligent search will fail without OpenAI API key"
    echo "Create with: modal secret create openai-secret OPENAI_API_KEY=\$OPENAI_API_KEY"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Deploy
echo ""
echo "🚀 Deploying to Modal Production"
echo "---------------------------------"

echo -e "${BLUE}Running: modal deploy main.py${NC}"
echo ""

if modal deploy main.py; then
    echo ""
    echo -e "${GREEN}✅ Deployment successful!${NC}"
    echo ""
    
    # Get production URL
    echo "🌐 Production Endpoint"
    echo "---------------------"
    echo "Your API is now live at:"
    echo "https://alemanb--treehacks-vector-search-web.modal.run"
    echo ""
    
    echo "📚 Available Endpoints:"
    echo "  GET  /health"
    echo "  POST /ingest"
    echo "  POST /ingest/batch"
    echo "  POST /search"
    echo "  POST /search/intelligent  ⭐ NEW"
    echo "  GET  /docs (Swagger UI)"
    echo ""
    
    echo "🧪 Test Production Endpoint:"
    echo "curl https://alemanb--treehacks-vector-search-web.modal.run/health"
    echo ""
    
    echo "📊 Monitor Logs:"
    echo "modal app logs treehacks-vector-search"
    echo ""
    
    echo -e "${GREEN}✅ Deployment Complete!${NC}"
else
    echo ""
    echo -e "${RED}❌ Deployment failed${NC}"
    echo "Check error messages above for details"
    exit 1
fi
