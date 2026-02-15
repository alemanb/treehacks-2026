# Implementation Guide: Pagination for Vector Search Results

## Status: READY FOR IMPLEMENTATION
## Date: 2026-02-14
## Estimated Time: 5-8 hours

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Backend Implementation](#2-backend-implementation)
3. [Frontend Implementation](#3-frontend-implementation)
4. [Testing & Validation](#4-testing--validation)
5. [Deployment](#5-deployment)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Prerequisites

### 1.1 Required Knowledge

- Python (FastAPI, Pydantic, Elasticsearch client)
- TypeScript/React (hooks, TanStack Table)
- Understanding of vector search and Elasticsearch kNN

### 1.2 Environment Setup

```bash
# Ensure Modal CLI is installed and authenticated
modal --version

# Verify Elasticsearch and Jina secrets are configured
modal secret list | grep -E "elastic-secret|jina-secret"

# Ensure frontend dependencies are installed
cd frontend
npm install
```

### 1.3 Backup Current State

```bash
# Create a feature branch
git checkout -b feature/pagination

# Backup current implementation files
cp modal/main.py modal/main.py.backup
cp modal/vectordb.py modal/vectordb.py.backup
cp modal/models.py modal/models.py.backup
```

---

## 2. Backend Implementation

### 2.1 Update Pydantic Models

**File**: `modal/models.py`

**Add new pagination models after existing models**:

```python
# Add after the SearchResult class

class PaginationMetadata(BaseModel):
    """Pagination metadata for search results."""
    page: int
    page_size: int
    total_results: int
    total_pages: int
```

**Update SearchRequest to include pagination parameters**:

```python
# Replace the existing SearchRequest class with:

class SearchRequest(BaseModel):
    """Request model for vector search with pagination."""
    query: str
    page: int = 1
    page_size: int = 10

    @field_validator('page')
    @classmethod
    def validate_page(cls, v: int) -> int:
        if v < 1:
            raise ValueError('page must be >= 1')
        return v

    @field_validator('page_size')
    @classmethod
    def validate_page_size(cls, v: int) -> int:
        if not (1 <= v <= 100):
            raise ValueError('page_size must be between 1 and 100')
        return v
```

**Update SearchResponse to include pagination metadata**:

```python
# Replace the existing SearchResponse class with:

class SearchResponse(BaseModel):
    """Response model for vector search with pagination metadata."""
    query: str
    results: list[SearchResult]
    pagination: PaginationMetadata
```

**Required import**:
```python
# Add at the top of the file if not present
from pydantic import field_validator
```

**Verification**:
```bash
# Test model validation
cd modal
python3 -c "
from models import SearchRequest

# Valid request
req = SearchRequest(query='test', page=2, page_size=10)
print(f'Valid: page={req.page}, page_size={req.page_size}')

# Invalid page
try:
    SearchRequest(query='test', page=0)
except ValueError as e:
    print(f'Caught expected error: {e}')

# Invalid page_size
try:
    SearchRequest(query='test', page_size=101)
except ValueError as e:
    print(f'Caught expected error: {e}')
"
```

---

### 2.2 Update Vector Search Function

**File**: `modal/vectordb.py`

**Replace the existing `search_similar()` function**:

```python
def search_similar(
    client: Elasticsearch,
    query_vector: list[float],
    page: int = 1,
    page_size: int = 10,
    max_page_size: int = 100,
) -> tuple[list[dict], int]:
    """Perform paginated kNN vector similarity search.

    Args:
        client: Elasticsearch client instance
        query_vector: 1024-dim embedding of the search query
        page: Current page number (1-indexed, default: 1)
        page_size: Results per page (default: 10, max: 100)
        max_page_size: Maximum allowed page_size (default: 100)

    Returns:
        Tuple of (results, total_count):
        - results: List of dicts with _id, _score, _source (content and metadata)
        - total_count: Total number of matching documents in the index

    Raises:
        ValueError: If page < 1 or page_size not in [1, max_page_size]

    Example:
        >>> hits, total = search_similar(es_client, query_emb, page=2, page_size=10)
        >>> print(f"Showing results 11-20 of {total}")

    Context7 Reference:
        /elastic/elasticsearch-py — kNN search with pagination via from_ and size
    """
    # Input validation
    if page < 1:
        raise ValueError("page must be >= 1")
    if not (1 <= page_size <= max_page_size):
        raise ValueError(f"page_size must be between 1 and {max_page_size}")

    # Calculate offset (0-indexed for Elasticsearch)
    offset = (page - 1) * page_size

    # Dynamic num_candidates scaling for deep pagination
    # Rule: num_candidates should be at least 10x (offset + page_size) for accuracy
    # Minimum of 1000 to ensure quality results for early pages
    num_candidates = max(1000, 10 * (offset + page_size))

    # Perform kNN search with pagination parameters
    response = client.search(
        index=ES_INDEX,
        knn={
            "field": "embedding",
            "query_vector": query_vector,
            "k": page_size,              # Number of results to return
            "num_candidates": num_candidates,  # Candidates to consider
        },
        from_=offset,                    # Skip offset results (0-indexed)
        size=page_size,                  # Return page_size results
        track_total_hits=True,           # Get accurate total count (not capped at 10k)
        _source=["content", "metadata"],  # Exclude embedding from response
    )

    # Extract results and total count
    hits = response["hits"]["hits"]

    # Get total count (handle both exact and estimated counts)
    total_info = response["hits"]["total"]
    if isinstance(total_info, dict):
        total_count = total_info["value"]
        # Note: total_info["relation"] can be "eq" (exact) or "gte" (estimated)
    else:
        total_count = total_info  # Older ES versions return int directly

    return hits, total_count
```

**Verification**:
```bash
# Test search_similar locally (requires ES connection)
cd modal
python3 -c "
from vectordb import get_client, search_similar
from embeddings import get_query_embedding

# Get ES client
es = get_client()

# Generate test query embedding
query_emb = get_query_embedding('test query')

# Test page 1
hits, total = search_similar(es, query_emb, page=1, page_size=10)
print(f'Page 1: {len(hits)} results, {total} total')

# Test page 2
hits, total = search_similar(es, query_emb, page=2, page_size=10)
print(f'Page 2: {len(hits)} results, {total} total')

# Test validation
try:
    search_similar(es, query_emb, page=0)
except ValueError as e:
    print(f'Validation works: {e}')
"
```

---

### 2.3 Update FastAPI Search Endpoint

**File**: `modal/main.py`

**Replace the existing `/search` endpoint** (lines 111-152):

```python
    @web_app.post("/search", response_model=SearchResponse)
    async def search(req: SearchRequest):
        """Vector similarity search endpoint with pagination.

        Embeds the query using Jina (retrieval.query task), performs kNN search
        in Elasticsearch with pagination support, and returns results with metadata.

        Request:
            {
                "query": "blue book stolen from library",
                "page": 1,
                "page_size": 10
            }

        Response:
            {
                "query": "...",
                "results": [{id, content, score, metadata}, ...],
                "pagination": {
                    "page": 1,
                    "page_size": 10,
                    "total_results": 47,
                    "total_pages": 5
                }
            }
        """
        # 1. Validate query
        if not req.query.strip():
            raise HTTPException(400, "query must be a non-empty string")

        # 2. Embed query using retrieval.query task
        try:
            query_embedding = get_query_embedding(req.query)
        except Exception as e:
            raise HTTPException(502, f"Embedding service error: {str(e)}")

        # 3. Perform paginated kNN search in Elasticsearch
        es = _get_es()
        try:
            hits, total_count = search_similar(
                es,
                query_embedding,
                page=req.page,
                page_size=req.page_size
            )
        except ValueError as e:
            # Validation errors (invalid page or page_size)
            raise HTTPException(400, str(e))
        except Exception as e:
            # ES connection or search errors
            raise HTTPException(503, f"Search service error: {str(e)}")

        # 4. Calculate pagination metadata
        # Use ceiling division to get total pages
        total_pages = (total_count + req.page_size - 1) // req.page_size

        # 5. Format response
        results = [
            SearchResult(
                id=hit["_id"],
                content=hit["_source"]["content"],
                score=hit["_score"],
                metadata=Metadata(**hit["_source"]["metadata"]),
            )
            for hit in hits
        ]

        return SearchResponse(
            query=req.query,
            results=results,
            pagination=PaginationMetadata(
                page=req.page,
                page_size=req.page_size,
                total_results=total_count,
                total_pages=total_pages
            )
        )
```

**Update imports** (at the top of the `web()` function, around line 26):

```python
    # Update the imports section to include PaginationMetadata
    from models import (
        BatchIngestRequest,
        BatchIngestResponse,
        HealthResponse,
        IngestRequest,
        IngestResponse,
        Metadata,
        PaginationMetadata,      # ADD THIS LINE
        SearchRequest,
        SearchResponse,
        SearchResult,
    )
```

---

### 2.4 Deploy Backend Changes

```bash
# Test imports locally
cd modal
python3 -c "from main import web; print('Imports successful')"

# Deploy to Modal
modal deploy main.py

# Verify deployment
modal app list | grep treehacks-vector-search

# Expected output:
# treehacks-vector-search  <deployment-id>  deployed  <timestamp>
```

---

### 2.5 Test Backend API

**Test default pagination (page 1, 10 results)**:
```bash
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": "blue book"}'
```

**Expected response**:
```json
{
  "query": "blue book",
  "results": [
    {"id": "...", "content": "...", "score": 0.9, "metadata": {...}},
    // ... up to 10 results
  ],
  "pagination": {
    "page": 1,
    "page_size": 10,
    "total_results": 25,
    "total_pages": 3
  }
}
```

**Test page 2**:
```bash
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": "blue book", "page": 2, "page_size": 10}'
```

**Test validation (should return 400 error)**:
```bash
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "page": 0}'
```

**Expected error**:
```json
{
  "detail": "page must be >= 1"
}
```

---

## 3. Frontend Implementation

### 3.1 Update TypeScript Types

**File**: `frontend/src/types/search.ts`

**Add pagination metadata type**:

```typescript
// Add after SearchResult interface

export interface PaginationMetadata {
  page: number
  page_size: number
  total_results: number
  total_pages: number
}
```

**Update SearchResponse interface**:

```typescript
// Replace existing SearchResponse interface

export interface SearchResponse {
  query: string
  results: SearchResult[]
  pagination: PaginationMetadata  // ADD THIS LINE
}
```

---

### 3.2 Update useSearch Hook

**File**: `frontend/src/hooks/useSearch.ts`

**Replace entire file content**:

```typescript
import { useCallback, useRef, useState } from "react"
import type { SearchResponse, SearchResult, PaginationMetadata } from "@/types/search"

const BACKEND_URL = "https://alemanb--treehacks-vector-search-web.modal.run"

interface UseSearchReturn {
  search: (query: string, page?: number) => void
  results: SearchResult[]
  pagination: PaginationMetadata | null
  isLoading: boolean
  error: string | null
  currentPage: number
  setPage: (page: number) => void
}

export function useSearch(onComplete?: () => void): UseSearchReturn {
  const [results, setResults] = useState<SearchResult[]>([])
  const [pagination, setPagination] = useState<PaginationMetadata | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentQuery, setCurrentQuery] = useState<string>("")
  const [currentPage, setCurrentPage] = useState<number>(1)
  const abortControllerRef = useRef<AbortController | null>(null)

  const search = useCallback(
    async (query: string, page: number = 1) => {
      setIsLoading(true)
      setError(null)
      setCurrentQuery(query)
      setCurrentPage(page)

      // Cancel previous request if still pending
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }

      abortControllerRef.current = new AbortController()

      try {
        const response = await fetch(`${BACKEND_URL}/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            page,
            page_size: 10,  // Fixed page size
          }),
          signal: abortControllerRef.current.signal,
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(
            errorData.detail || `Search failed: ${response.statusText}`,
          )
        }

        const data: SearchResponse = await response.json()

        // Filter to only show observations with motion data
        const filteredResults = data.results.filter(
          (r) => r.metadata.motion_vector !== null
        )

        setResults(filteredResults)
        setPagination(data.pagination)
        onComplete?.()
      } catch (err) {
        // Don't set error if request was aborted (user started new search)
        if (err instanceof Error && err.name !== "AbortError") {
          setError(err.message || "An unknown error occurred")
        }
      } finally {
        setIsLoading(false)
        abortControllerRef.current = null
      }
    },
    [onComplete],
  )

  const setPage = useCallback(
    (page: number) => {
      if (currentQuery && pagination && page >= 1 && page <= pagination.total_pages) {
        search(currentQuery, page)
      }
    },
    [currentQuery, pagination, search]
  )

  return { search, results, pagination, isLoading, error, currentPage, setPage }
}
```

---

### 3.3 Update DataTableView Component

**File**: `frontend/src/components/data-table/DataTableView.tsx`

**Replace entire file content**:

```typescript
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table"
import type { SearchResult, PaginationMetadata } from "@/types/search"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { columns } from "./columns"

interface DataTableViewProps {
  results: SearchResult[]
  pagination: PaginationMetadata | null
  onPageChange: (page: number) => void
  isLoading?: boolean
}

export function DataTableView({
  results,
  pagination,
  onPageChange,
  isLoading = false,
}: DataTableViewProps) {
  const table = useReactTable({
    data: results,
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,  // Server-side pagination
    pageCount: pagination?.total_pages ?? 0,
  })

  return (
    <div className="space-y-4">
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  {isLoading ? "Loading..." : "No results."}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {pagination && pagination.total_pages > 1 && (
        <div className="flex items-center justify-between px-2">
          <div className="text-sm text-muted-foreground">
            Showing {((pagination.page - 1) * pagination.page_size) + 1} to{" "}
            {Math.min(pagination.page * pagination.page_size, pagination.total_results)} of{" "}
            {pagination.total_results} results
          </div>
          <div className="flex items-center space-x-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(pagination.page - 1)}
              disabled={pagination.page === 1 || isLoading}
            >
              Previous
            </Button>
            <div className="text-sm font-medium">
              Page {pagination.page} of {pagination.total_pages}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(pagination.page + 1)}
              disabled={pagination.page === pagination.total_pages || isLoading}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
```

---

### 3.4 Update Parent Component (ResultsPhase)

**File**: `frontend/src/components/investigation/ResultsPhase.tsx`

**Find the `DataTableView` usage** (around line 20-30) and update it:

```typescript
// Before (existing code):
<DataTableView results={results} />

// After (updated code):
<DataTableView
  results={results}
  pagination={pagination}
  onPageChange={setPage}
  isLoading={isLoading}
/>
```

**Update the hook usage** (around line 10-15):

```typescript
// Before (existing code):
const { search, results, isLoading, error } = useSearch(handleComplete)

// After (updated code):
const { search, results, pagination, isLoading, error, setPage } = useSearch(handleComplete)
```

---

### 3.5 Build and Test Frontend

```bash
cd frontend

# Install dependencies (if not already installed)
npm install

# Run type checking
npm run lint

# Build for production
npm run build

# Run dev server for testing
npm run dev
```

**Manual testing steps**:

1. Open browser to `http://localhost:5173`
2. Perform a search query (e.g., "blue book")
3. Verify 10 results are displayed (if available)
4. Click "Next" button → should load page 2
5. Verify different results are shown
6. Click "Previous" button → should return to page 1
7. Navigate to last page → "Next" button should be disabled
8. Perform new search → should reset to page 1

---

## 4. Testing & Validation

### 4.1 Backend Integration Tests

**Create test script**: `modal/test_pagination.py`

```python
import requests

BASE_URL = "https://alemanb--treehacks-vector-search-web.modal.run"

def test_default_pagination():
    """Test default pagination (page 1, 10 results)."""
    response = requests.post(
        f"{BASE_URL}/search",
        json={"query": "test query"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "pagination" in data
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["page_size"] == 10
    assert len(data["results"]) <= 10
    print("✓ Default pagination test passed")

def test_page_2():
    """Test page 2 returns different results."""
    # Get page 1
    response1 = requests.post(
        f"{BASE_URL}/search",
        json={"query": "test query", "page": 1}
    )
    data1 = response1.json()
    ids_page1 = {r["id"] for r in data1["results"]}

    # Get page 2
    response2 = requests.post(
        f"{BASE_URL}/search",
        json={"query": "test query", "page": 2}
    )
    data2 = response2.json()
    ids_page2 = {r["id"] for r in data2["results"]}

    # Verify no overlap
    assert ids_page1.isdisjoint(ids_page2), "Pages have duplicate results"
    print("✓ Page 2 test passed (no duplicates)")

def test_validation_errors():
    """Test invalid pagination parameters."""
    # Invalid page 0
    response = requests.post(
        f"{BASE_URL}/search",
        json={"query": "test", "page": 0}
    )
    assert response.status_code == 400
    print("✓ Page 0 validation test passed")

    # Invalid page_size 101
    response = requests.post(
        f"{BASE_URL}/search",
        json={"query": "test", "page_size": 101}
    )
    assert response.status_code == 400
    print("✓ Page size validation test passed")

def test_total_count_accuracy():
    """Test total_results matches actual count."""
    response = requests.post(
        f"{BASE_URL}/search",
        json={"query": "test query"}
    )
    data = response.json()
    total = data["pagination"]["total_results"]
    page_size = data["pagination"]["page_size"]
    total_pages = data["pagination"]["total_pages"]

    # Verify total_pages calculation
    expected_pages = (total + page_size - 1) // page_size
    assert total_pages == expected_pages
    print(f"✓ Total count test passed ({total} results, {total_pages} pages)")

if __name__ == "__main__":
    print("Running pagination integration tests...\n")
    test_default_pagination()
    test_page_2()
    test_validation_errors()
    test_total_count_accuracy()
    print("\n✅ All tests passed!")
```

**Run tests**:
```bash
cd modal
python3 test_pagination.py
```

### 4.2 Frontend E2E Testing Checklist

- [ ] Search displays results on page 1 by default
- [ ] Pagination controls appear when results > 10
- [ ] "Previous" button is disabled on page 1
- [ ] "Next" button is disabled on last page
- [ ] Page indicator shows correct "Page X of Y"
- [ ] Result count shows correct "Showing X to Y of Z"
- [ ] Clicking "Next" loads page 2 with different results
- [ ] Clicking "Previous" returns to page 1
- [ ] Loading state displays during page transitions
- [ ] New search resets pagination to page 1
- [ ] Empty results hide pagination controls
- [ ] Error messages display correctly

### 4.3 Performance Testing

**Test pagination latency**:

```bash
# Test page 1 latency (should be <500ms)
time curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "page": 1}'

# Test page 5 latency (should be <1000ms)
time curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "page": 5}'

# Test page 10 latency (should be <1500ms)
time curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "page": 10}'
```

---

## 5. Deployment

### 5.1 Backend Deployment

```bash
cd modal

# Final deployment to production
modal deploy main.py

# Verify health endpoint
curl https://alemanb--treehacks-vector-search-web.modal.run/health

# Test production search endpoint
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}'
```

### 5.2 Frontend Deployment

```bash
cd frontend

# Build production bundle
npm run build

# Verify build output
ls -lh dist/

# Deploy to hosting platform (Vercel, Netlify, etc.)
# Example for Vercel:
# npx vercel --prod

# Or serve locally for testing:
npm run preview
```

### 5.3 Post-Deployment Verification

**Smoke Tests**:
1. Visit production frontend URL
2. Perform search query
3. Navigate through pages 1-3
4. Verify pagination controls work
5. Check browser console for errors
6. Test on mobile device

**Monitoring**:
```bash
# Monitor Modal logs
modal app logs treehacks-vector-search

# Monitor for errors
modal app logs treehacks-vector-search --filter error

# Check latency metrics
modal app stats treehacks-vector-search
```

---

## 6. Troubleshooting

### 6.1 Common Backend Issues

**Issue**: `ImportError: cannot import name 'PaginationMetadata'`

**Solution**:
```bash
# Verify models.py has PaginationMetadata class
grep -n "class PaginationMetadata" modal/models.py

# Verify main.py imports it
grep -n "PaginationMetadata" modal/main.py

# Redeploy
modal deploy modal/main.py
```

---

**Issue**: `ValueError: page must be >= 1` for valid requests

**Solution**:
```python
# Check SearchRequest validator in models.py
# Ensure @field_validator decorator is correct:

@field_validator('page')
@classmethod
def validate_page(cls, v: int) -> int:
    if v < 1:
        raise ValueError('page must be >= 1')
    return v
```

---

**Issue**: Empty results on page 2+ but results exist

**Solution**:
```python
# Check num_candidates calculation in vectordb.py
# Increase minimum value:

num_candidates = max(2000, 10 * (offset + page_size))  # Increased from 1000
```

---

**Issue**: Total count is capped at 10,000

**Solution**:
```python
# Ensure track_total_hits=True in vectordb.py search_similar():

response = client.search(
    # ...
    track_total_hits=True,  # Must be True for accurate counts
)
```

---

### 6.2 Common Frontend Issues

**Issue**: TypeScript error: `Property 'pagination' does not exist on type 'SearchResponse'`

**Solution**:
```typescript
// Verify types/search.ts has PaginationMetadata:
export interface PaginationMetadata {
  page: number
  page_size: number
  total_results: number
  total_pages: number
}

export interface SearchResponse {
  query: string
  results: SearchResult[]
  pagination: PaginationMetadata  // Add this line
}
```

---

**Issue**: Pagination controls not appearing

**Solution**:
1. Check that `pagination` prop is passed to `DataTableView`
2. Verify `pagination.total_pages > 1` condition
3. Check browser console for errors
4. Verify API response includes pagination metadata:
   ```javascript
   console.log('API response:', data)
   console.log('Pagination:', data.pagination)
   ```

---

**Issue**: "Next" button always disabled

**Solution**:
```typescript
// Check button disabled logic in DataTableView.tsx:
disabled={pagination.page === pagination.total_pages || isLoading}

// Debug:
console.log('Current page:', pagination.page)
console.log('Total pages:', pagination.total_pages)
console.log('Is loading:', isLoading)
```

---

**Issue**: Page doesn't change when clicking buttons

**Solution**:
```typescript
// Verify onPageChange is passed correctly:
<DataTableView
  results={results}
  pagination={pagination}
  onPageChange={setPage}  // Must be the setPage function from useSearch
  isLoading={isLoading}
/>

// Verify setPage function is called:
onClick={() => {
  console.log('Changing to page:', pagination.page + 1)
  onPageChange(pagination.page + 1)
}}
```

---

### 6.3 Performance Issues

**Issue**: Slow page load (>2 seconds) for pages 5+

**Solution**:
```python
# Increase num_candidates in vectordb.py:
num_candidates = max(3000, 15 * (offset + page_size))  # Increased multiplier

# Or reduce page_size to 5-8 results per page
```

---

**Issue**: High memory usage in Elasticsearch

**Solution**:
1. Monitor ES cluster metrics
2. Consider adding filters to reduce search space:
   ```python
   response = client.search(
       # ...
       query={
           "bool": {
               "filter": [
                   {"range": {"timestamp": {"gte": "now-30d"}}}  # Last 30 days only
               ]
           }
       }
   )
   ```

---

### 6.4 Validation Issues

**Issue**: Users can request page 1000 (resource exhaustion risk)

**Solution**:
```python
# Add maximum offset check in main.py search endpoint:

MAX_OFFSET = 1000  # Maximum results that can be skipped

offset = (req.page - 1) * req.page_size
if offset > MAX_OFFSET:
    raise HTTPException(
        400,
        f"Maximum pagination depth exceeded (page {req.page}). "
        f"Please refine your search query."
    )
```

---

## 7. Rollback Plan

If critical issues arise, rollback to the previous version:

```bash
# Backend rollback
cd modal
cp main.py.backup main.py
cp vectordb.py.backup vectordb.py
cp models.py.backup models.py
modal deploy main.py

# Frontend rollback
git checkout HEAD~1 -- frontend/src/

# Verify rollback
curl https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}'

# Should return top 3 results (old behavior)
```

---

## 8. Success Criteria Checklist

Before marking implementation complete, verify:

### Backend
- [ ] `/search` endpoint accepts `page` and `page_size` parameters
- [ ] Response includes `pagination` metadata object
- [ ] Validation errors return 400 status codes
- [ ] Page 2+ returns different results than page 1
- [ ] Total count is accurate (not capped at 10k)
- [ ] Performance: p95 latency < 1s for pages 1-5
- [ ] No duplicate results across pages

### Frontend
- [ ] Pagination controls display when results > 10
- [ ] "Previous" and "Next" buttons work correctly
- [ ] Page indicator shows current page and total pages
- [ ] Result count shows correct range (e.g., "1-10 of 47")
- [ ] Loading state displays during page transitions
- [ ] New search resets to page 1
- [ ] Edge cases handled gracefully (empty results, last page)

### Integration
- [ ] End-to-end flow works: search → page 1 → page 2 → page 3
- [ ] No console errors in browser
- [ ] No 500 errors in Modal logs
- [ ] Mobile responsive design works correctly

---

## 9. Documentation Updates

After successful implementation, update:

1. **README.md** (if exists):
   - Add pagination feature to feature list
   - Update API examples to show pagination params

2. **API Documentation**:
   - Document pagination parameters and response format
   - Add example requests/responses

3. **CHANGELOG.md** (create if doesn't exist):
   ```markdown
   ## [1.1.0] - 2026-02-14
   ### Added
   - Pagination support for search results (10 results per page)
   - Frontend pagination controls (Previous/Next buttons)
   - Total result count and page navigation
   ```

---

## 10. Next Steps

After pagination is working:

1. **Analytics Tracking**:
   - Add event tracking for pagination usage
   - Monitor which pages users visit most

2. **Performance Optimization**:
   - Implement result caching if needed
   - Pre-fetch next page in background

3. **UX Enhancements**:
   - Add "Jump to page" input
   - Implement keyboard shortcuts (arrow keys)
   - Add loading skeletons instead of spinner

4. **Advanced Features**:
   - Configurable page size (10/25/50)
   - Cursor-based pagination for strict consistency
   - URL state persistence (bookmarkable page numbers)

---

## Appendix: Quick Reference Commands

```bash
# Backend deployment
cd modal && modal deploy main.py

# Frontend build
cd frontend && npm run build

# Run backend tests
cd modal && python3 test_pagination.py

# Check logs
modal app logs treehacks-vector-search

# Test API
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "page": 2, "page_size": 10}'
```

---

**Implementation Complete!** 🎉

You now have a fully functional paginated search system that allows users to browse through all vector search results with a clean, intuitive interface.
