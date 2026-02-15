# Design: Pagination for Vector Search Results

## Status: PLANNED
## Date: 2026-02-14

---

## 1. Overview

Enhance the existing vector search API and frontend data table to support pagination, allowing users to browse through all potential matches from the RAG database instead of being limited to the top 3 results. The system will support page-based navigation with a configurable page size (defaulting to 10 results per page).

### Goals

- Enable pagination in the `/search` endpoint with page and page_size parameters
- Return paginated results with metadata (total count, current page, total pages)
- Update frontend DataTableView to display 10 results per page with pagination controls
- Maintain existing search functionality and performance characteristics
- Provide smooth user experience when navigating between pages

### Non-Goals

- Cursor-based pagination (offset-based is sufficient for this use case)
- Infinite scroll (discrete pages provide better user control)
- Client-side caching of all results (fetch on-demand per page)
- Sort/filter controls (vector similarity is the primary ordering)

---

## 2. Architecture

### 2.1 System Context

```
┌──────────────────────┐
│  Frontend UI         │
│  (React + TanStack   │
│   Table)             │
│                      │
│  • Page controls     │
│  • Results display   │
│  • Page size: 10     │
└──────────┬───────────┘
           │
           │ POST /search
           │ { query, page, page_size }
           │
           ▼
┌──────────────────────────────────────────┐
│  Modal App (FastAPI)                     │
│                                          │
│  1. Validate pagination params           │
│  2. Calculate offset: (page-1)*page_size │
│  3. Embed query via Jina                 │
│  4. kNN search with size & from params   │
│  5. Get total count from ES              │
│  6. Return paginated results + metadata  │
└──────────┬───────────────────────────────┘
           │
           ▼
┌──────────────────────────┐
│  Elasticsearch           │
│                          │
│  • kNN search with from  │
│  • size parameters       │
│  • Track total hits      │
└──────────────────────────┘
```

### 2.2 Integration Points

| Component | Current State | Changes Required |
|-----------|--------------|------------------|
| **Backend `/search` endpoint** | Returns top 3 results | Accept `page`, `page_size` params; return pagination metadata |
| **`search_similar()` function** | Fixed k=3 | Support offset (`from`) and limit (`size`) parameters |
| **Pydantic Models** | `SearchRequest`, `SearchResponse` | Add pagination fields to request and response |
| **Frontend `useSearch` hook** | Single API call | Track current page, handle page changes |
| **`DataTableView` component** | No pagination | Add TanStack Table pagination features |
| **shadcn UI components** | No pagination controls | Add pagination component |

### 2.3 Data Flow

```
User clicks "Next Page"
    │
    ▼
Frontend updates page state (page++)
    │
    ▼
API call: POST /search { query, page: 2, page_size: 10 }
    │
    ▼
Backend calculates offset: (2-1) * 10 = 10
    │
    ▼
Elasticsearch kNN search with from=10, size=10
    │
    ▼
Backend returns results[10-19] + pagination metadata
    │
    ▼
Frontend updates table with new results
    │
    ▼
UI shows "Page 2 of N" with navigation controls
```

---

## 3. Input/Output Schema

### 3.1 Updated Search Request

**Endpoint**: `POST /search`

**Request Body**:
```json
{
  "query": "blue book stolen from library",
  "page": 1,
  "page_size": 10
}
```

**New Fields**:
| Field | Type | Required | Default | Validation | Description |
|-------|------|----------|---------|------------|-------------|
| `page` | `integer` | No | 1 | ≥1 | Current page number (1-indexed) |
| `page_size` | `integer` | No | 10 | 1-100 | Results per page (capped at 100) |

### 3.2 Updated Search Response

**Response Body** (200 OK):
```json
{
  "query": "blue book stolen from library",
  "results": [
    {
      "id": "es_doc_id_001",
      "content": "Blue hardcover book detected on shelf",
      "score": 0.92,
      "metadata": {
        "object": "book",
        "color": "blue",
        "timestamp": "2026-02-10T09:15:00Z",
        "motion_vector": [0.3, -0.1],
        "device_id": "jetson_01"
      }
    }
    // ... 9 more results (10 total per page)
  ],
  "pagination": {
    "page": 1,
    "page_size": 10,
    "total_results": 47,
    "total_pages": 5
  }
}
```

**New `pagination` Object**:
| Field | Type | Description |
|-------|------|-------------|
| `page` | `integer` | Current page number (echoed from request) |
| `page_size` | `integer` | Results per page (echoed from request) |
| `total_results` | `integer` | Total number of matching documents in ES |
| `total_pages` | `integer` | Calculated: `ceil(total_results / page_size)` |

### 3.3 Backward Compatibility

**Old Request Format** (no pagination params):
```json
{
  "query": "blue book"
}
```

**Behavior**: Defaults to `page=1`, `page_size=10` (returns first 10 results instead of 3)

**Migration Strategy**:
- Frontend can continue to work without changes initially
- Update frontend to send pagination params explicitly
- Eventually deprecate the default behavior if needed

---

## 4. Backend Design

### 4.1 Elasticsearch Pagination

Elasticsearch supports offset-based pagination via `from` and `size` parameters:

```python
response = client.search(
    index="observations-v1",
    knn={
        "field": "embedding",
        "query_vector": query_embedding,
        "k": page_size,              # Number of results per page
        "num_candidates": 1000       # Increased from 100 for better recall
    },
    from_=offset,                    # Skip offset results (0-indexed)
    size=page_size,                  # Return page_size results
    track_total_hits=True            # Get accurate total count
)
```

**Key Parameters**:
- **`from_`**: Offset (0-indexed): `(page - 1) * page_size`
- **`size`**: Number of results to return per page
- **`track_total_hits`**: `True` to get accurate total (default is 10,000 cap)
- **`num_candidates`**: Increased to 1000 to ensure enough candidates for pagination

**Important**: Elasticsearch kNN + pagination requires careful tuning:
- `num_candidates` should be significantly larger than `from_ + size`
- For deep pagination (page 5+), `num_candidates` should be ≥ `offset + page_size`
- Performance degrades with very deep pagination (page 100+)

### 4.2 Updated `search_similar()` Function

**New Signature**:
```python
def search_similar(
    client: Elasticsearch,
    query_vector: list[float],
    page: int = 1,
    page_size: int = 10,
    max_page_size: int = 100
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
        - results: List of dicts with _id, _score, _source
        - total_count: Total number of matching documents

    Raises:
        ValueError: If page < 1 or page_size not in [1, max_page_size]
    """
    # Validation
    if page < 1:
        raise ValueError("page must be >= 1")
    if not (1 <= page_size <= max_page_size):
        raise ValueError(f"page_size must be between 1 and {max_page_size}")

    # Calculate offset
    offset = (page - 1) * page_size

    # Adjust num_candidates for pagination depth
    # Rule of thumb: num_candidates should be at least 10x (offset + page_size)
    num_candidates = max(1000, 10 * (offset + page_size))

    # Perform kNN search with pagination
    response = client.search(
        index=ES_INDEX,
        knn={
            "field": "embedding",
            "query_vector": query_vector,
            "k": page_size,
            "num_candidates": num_candidates,
        },
        from_=offset,
        size=page_size,
        track_total_hits=True,
        _source=["content", "metadata"],
    )

    # Extract results and total count
    hits = response["hits"]["hits"]
    total = response["hits"]["total"]["value"]  # or ["relation"] == "gte"

    return hits, total
```

**Considerations**:
- **Deep Pagination Performance**: Offset-based pagination gets slower as offset increases
- **num_candidates Scaling**: Dynamically adjust based on pagination depth
- **Total Count Accuracy**: `track_total_hits=True` ensures accurate count (may be slower)

### 4.3 Updated Pydantic Models

**In `models.py`**:

```python
class SearchRequest(BaseModel):
    query: str
    page: int = 1                    # Default to page 1
    page_size: int = 10              # Default to 10 results per page

    @field_validator('page')
    def validate_page(cls, v):
        if v < 1:
            raise ValueError('page must be >= 1')
        return v

    @field_validator('page_size')
    def validate_page_size(cls, v):
        if not (1 <= v <= 100):
            raise ValueError('page_size must be between 1 and 100')
        return v


class PaginationMetadata(BaseModel):
    page: int
    page_size: int
    total_results: int
    total_pages: int


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    pagination: PaginationMetadata
```

### 4.4 Updated `/search` Endpoint

**In `main.py`**:

```python
@web_app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    """Vector similarity search endpoint with pagination.

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
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(503, f"Search service error: {str(e)}")

    # 4. Calculate pagination metadata
    total_pages = (total_count + req.page_size - 1) // req.page_size  # Ceiling division

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

---

## 5. Frontend Design

### 5.1 Updated Search Types

**In `src/types/search.ts`**:

```typescript
export interface PaginationMetadata {
  page: number
  page_size: number
  total_results: number
  total_pages: number
}

export interface SearchResponse {
  query: string
  results: SearchResult[]
  pagination: PaginationMetadata
}
```

### 5.2 Updated `useSearch` Hook

**In `src/hooks/useSearch.ts`**:

```typescript
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
            page_size: 10  // Fixed page size
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

### 5.3 Updated DataTableView Component

**In `src/components/data-table/DataTableView.tsx`**:

```typescript
import { useState } from "react"
import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
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
  isLoading = false
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
            <div className="text-sm">
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

### 5.4 Parent Component Integration

**In `src/components/investigation/ResultsPhase.tsx`** (example):

```typescript
// Update to pass pagination props
<DataTableView
  results={searchResults}
  pagination={pagination}
  onPageChange={handlePageChange}
  isLoading={isLoading}
/>
```

---

## 6. Performance Considerations

### 6.1 Elasticsearch Pagination Performance

| Page Depth | Offset | Performance Impact | Mitigation |
|------------|--------|-------------------|------------|
| Pages 1-5 | 0-50 | Minimal (<100ms overhead) | Standard `num_candidates=1000` |
| Pages 6-10 | 51-100 | Moderate (100-200ms overhead) | Increase `num_candidates=2000` |
| Pages 11+ | 100+ | Significant (>200ms overhead) | Consider search refinement UI hints |

**Optimization Strategy**:
- Dynamic `num_candidates` scaling: `max(1000, 10 * (offset + page_size))`
- Monitor p95 latency for pages beyond page 10
- Add loading indicators for deep pagination
- Consider "refine search" prompts for pages 5+

### 6.2 Memory & Network

| Aspect | Current (top 3) | With Pagination (10/page) | Impact |
|--------|----------------|---------------------------|---------|
| ES memory | ~3 results in memory | ~10 results in memory | +7KB per request |
| Network payload | ~2KB | ~6KB | +4KB per request |
| Frontend render | 3 rows | 10 rows | +7 DOM nodes |
| Total impact | | | Negligible |

**Key Insight**: Pagination actually reduces total memory usage compared to loading all results upfront.

### 6.3 Cost Analysis

| Service | Cost Impact | Calculation |
|---------|------------|-------------|
| Elasticsearch | Minimal | Same kNN search, slightly more candidates |
| Jina API | None | Same query embedding (not re-embedded per page) |
| Modal | Negligible | Slightly longer compute time per request |
| **Total** | **<5% increase** | Well within budget |

---

## 7. Error Handling & Edge Cases

### 7.1 Invalid Pagination Parameters

| Scenario | Status | Response | UI Behavior |
|----------|--------|----------|-------------|
| `page < 1` | 400 | `{"detail": "page must be >= 1"}` | Show error message, reset to page 1 |
| `page_size > 100` | 400 | `{"detail": "page_size must be between 1 and 100"}` | Clamp to max 100 |
| `page > total_pages` | 200 | `{"results": [], "pagination": {...}}` | Show "No results on this page" |
| `page_size < 1` | 400 | `{"detail": "page_size must be >= 1"}` | Reset to default 10 |

### 7.2 Empty Results Handling

**Scenario**: User navigates to page 3, but there are only 2 pages of results

**Backend Behavior**: Returns empty results array with accurate pagination metadata
```json
{
  "query": "...",
  "results": [],
  "pagination": {
    "page": 3,
    "page_size": 10,
    "total_results": 15,
    "total_pages": 2
  }
}
```

**Frontend Behavior**:
1. Detect `results.length === 0` and `page > total_pages`
2. Automatically navigate back to last valid page
3. Show informative message: "No more results. Showing page 2."

### 7.3 Concurrent Search Handling

**Scenario**: User types new query while on page 2 of previous search

**Frontend Behavior**:
1. Abort previous request via `AbortController`
2. Reset `currentPage` to 1
3. Execute new search from page 1
4. Clear previous pagination state

---

## 8. Testing Strategy

### 8.1 Backend Unit Tests

| Test Case | Input | Expected Output |
|-----------|-------|-----------------|
| Default pagination | `{"query": "test"}` | `page=1, page_size=10` |
| Valid page 2 | `{"query": "test", "page": 2}` | Results 11-20, correct pagination metadata |
| Max page_size | `{"query": "test", "page_size": 100}` | 100 results (if available) |
| Invalid page 0 | `{"query": "test", "page": 0}` | 400 error |
| Invalid page_size 101 | `{"query": "test", "page_size": 101}` | 400 error |
| Page beyond results | `{"query": "test", "page": 999}` | Empty results, valid metadata |
| Total count accuracy | Search with known result count | `pagination.total_results` matches ES count |

### 8.2 Integration Tests

**Test: End-to-End Pagination**
1. Ingest 25 test documents with embeddings
2. Search query expected to match all 25
3. Request page 1 → Assert 10 results, `total_results=25`, `total_pages=3`
4. Request page 2 → Assert 10 results, different IDs from page 1
5. Request page 3 → Assert 5 results
6. Request page 4 → Assert 0 results

**Test: Pagination Consistency**
1. Perform same search with `page=1` and `page=2`
2. Assert no duplicate IDs between pages
3. Assert scores are monotonically decreasing across pages

### 8.3 Frontend E2E Tests

| User Action | Expected Behavior |
|------------|-------------------|
| Search query → See results | Page 1 displayed, pagination shows "Page 1 of N" |
| Click "Next" button | Page 2 loads, different results, button shows "Page 2 of N" |
| Click "Previous" button | Returns to page 1, original results restored |
| Navigate to last page | "Next" button disabled |
| Navigate to first page | "Previous" button disabled |
| New search while on page 2 | Resets to page 1 of new results |
| Empty search | No pagination controls shown |

---

## 9. Security Considerations

### 9.1 Input Validation

- **Page Parameter**: Already validated via Pydantic (`>= 1`)
- **Page Size Parameter**: Capped at 100 to prevent resource exhaustion
- **Deep Pagination Limits**: Consider blocking pages > 50 to prevent abuse
- **Rate Limiting**: Existing 10 req/min limit applies to paginated searches

### 9.2 Resource Protection

**Potential Attack**: Requesting page 1000 with `page_size=100` to exhaust ES resources

**Mitigation**:
1. Add maximum offset check: `offset = (page - 1) * page_size`
2. If `offset > 1000`, return 400 error: "Maximum pagination depth exceeded"
3. Log deep pagination attempts for monitoring

### 9.3 Data Consistency

- **Race Condition**: Results may change between page requests if new documents are indexed
- **Mitigation**: Accept eventual consistency (standard for search UIs)
- **Future Enhancement**: Add `search_after` cursor-based pagination for strict consistency

---

## 10. Implementation Checklist

### Phase 1: Backend Pagination (2-3 hours)

- [ ] Update `search_similar()` in `vectordb.py` to accept page/page_size and return total count
- [ ] Add `PaginationMetadata` model to `models.py`
- [ ] Update `SearchRequest` to include `page` and `page_size` fields with validation
- [ ] Update `SearchResponse` to include `pagination` field
- [ ] Modify `/search` endpoint in `main.py` to handle pagination
- [ ] Add input validation and error handling for edge cases
- [ ] Test locally with curl commands

### Phase 2: Frontend Pagination UI (2-3 hours)

- [ ] Update `SearchResponse` type in `src/types/search.ts` to include `pagination`
- [ ] Modify `useSearch` hook to track current page and handle page changes
- [ ] Update `DataTableView` to accept pagination props and render controls
- [ ] Add pagination UI with Previous/Next buttons and page indicator
- [ ] Handle loading states during page transitions
- [ ] Test UI navigation flow

### Phase 3: Integration & Testing (1-2 hours)

- [ ] Deploy backend changes to Modal
- [ ] Update frontend to use paginated API
- [ ] Test end-to-end pagination flow with real data
- [ ] Verify edge cases (empty results, last page, first page)
- [ ] Monitor performance for pages 1-10
- [ ] Document any issues or limitations

### Phase 4: Polish & Optimization (Optional, 1-2 hours)

- [ ] Add keyboard shortcuts (arrow keys for prev/next)
- [ ] Implement "Jump to page" input
- [ ] Add loading skeletons for better UX
- [ ] Monitor and optimize deep pagination performance
- [ ] Add analytics for pagination usage patterns

---

## 11. Success Criteria

| Metric | Target | Validation Method |
|--------|--------|-------------------|
| Pagination accuracy | 100% correct page boundaries | Manual testing + automated tests |
| Performance (pages 1-5) | p95 < 800ms | Load test with production data |
| Performance (pages 6-10) | p95 < 1200ms | Load test with production data |
| Error rate | <1% | Monitor production logs for 1 week |
| User engagement | >30% users navigate to page 2+ | Analytics tracking |
| Zero duplicate results | No duplicates across pages | Automated consistency test |

---

## 12. Future Enhancements

### 12.1 Advanced Pagination Features

- **Cursor-based Pagination**: Use Elasticsearch `search_after` for strict consistency
- **Jump to Page**: Add input field to jump directly to specific page
- **Configurable Page Size**: Allow users to choose 10/25/50/100 results per page
- **Infinite Scroll**: Alternative UI pattern for continuous browsing

### 12.2 Performance Optimizations

- **Result Caching**: Cache query embeddings and results for repeated searches
- **Pre-fetching**: Fetch next page in background while user views current page
- **Virtualized Scrolling**: Render only visible rows for very large page sizes
- **Index Optimization**: Tune ES index settings for better pagination performance

### 12.3 User Experience

- **Pagination State in URL**: Store page number in URL query params for bookmarking
- **Keyboard Navigation**: Arrow keys, Page Up/Down shortcuts
- **Loading Skeletons**: Better visual feedback during page transitions
- **Result Highlighting**: Maintain scroll position when navigating back

---

## 13. Dependencies Summary

### Backend Changes
| File | Changes | Lines of Code |
|------|---------|---------------|
| `vectordb.py` | Update `search_similar()` function | ~30 lines |
| `models.py` | Add `PaginationMetadata`, update request/response models | ~15 lines |
| `main.py` | Update `/search` endpoint handler | ~10 lines |

### Frontend Changes
| File | Changes | Lines of Code |
|------|---------|---------------|
| `src/types/search.ts` | Add `PaginationMetadata` type | ~6 lines |
| `src/hooks/useSearch.ts` | Add pagination state and handlers | ~20 lines |
| `src/components/data-table/DataTableView.tsx` | Add pagination UI and controls | ~40 lines |

### Total Implementation Effort
- **Backend**: ~2-3 hours
- **Frontend**: ~2-3 hours
- **Testing**: ~1-2 hours
- **Total**: ~5-8 hours

---

## 14. Key Design Decisions

### 14.1 Why Offset-Based Over Cursor-Based?

**Offset-Based Pros**:
- Simpler implementation
- Familiar page numbers for users
- Direct page jumping capability
- Sufficient for search use case (eventual consistency acceptable)

**Cursor-Based Cons**:
- More complex implementation
- No direct page jumping
- Overkill for non-critical search results

**Decision**: Offset-based is optimal for this use case; cursor-based can be added later if needed.

### 14.2 Why Page Size 10?

- **Usability**: 10 results fit comfortably on screen without scrolling
- **Performance**: Small enough to load quickly, large enough to reduce pagination frequency
- **Industry Standard**: Common page size for search interfaces (Google, Amazon)
- **Configurable**: Can be adjusted via frontend if user preference emerges

### 14.3 Why Server-Side Over Client-Side Pagination?

**Server-Side Pros**:
- Reduced initial load time (don't fetch all results)
- Lower memory usage on frontend
- Better for large result sets (100+ results)
- Scales with database growth

**Client-Side Cons**:
- Would require fetching all results upfront
- Poor UX for slow connections
- Wasteful if user only views page 1

**Decision**: Server-side pagination is essential for scalability and performance.

### 14.4 Why Manual Pagination with TanStack Table?

TanStack Table supports built-in pagination, but we use `manualPagination: true` because:
- Pagination logic is server-side, not client-side
- Page count comes from backend (`total_pages`)
- Table only manages UI state, not data fetching
- Cleaner separation of concerns

---

## Appendix A: Example API Interactions

### Request Page 1 (Default)
```bash
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": "blue backpack"}'
```

**Response**:
```json
{
  "query": "blue backpack",
  "results": [
    {
      "id": "001",
      "content": "Blue backpack on desk near window",
      "score": 0.95,
      "metadata": {...}
    },
    // ... 9 more results
  ],
  "pagination": {
    "page": 1,
    "page_size": 10,
    "total_results": 47,
    "total_pages": 5
  }
}
```

### Request Page 2
```bash
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "blue backpack",
    "page": 2,
    "page_size": 10
  }'
```

**Response**:
```json
{
  "query": "blue backpack",
  "results": [
    {
      "id": "011",
      "content": "Backpack left on bench outside",
      "score": 0.82,
      "metadata": {...}
    },
    // ... 9 more results (IDs 011-020)
  ],
  "pagination": {
    "page": 2,
    "page_size": 10,
    "total_results": 47,
    "total_pages": 5
  }
}
```

### Request Last Page
```bash
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "blue backpack",
    "page": 5,
    "page_size": 10
  }'
```

**Response**:
```json
{
  "query": "blue backpack",
  "results": [
    {
      "id": "041",
      "content": "Blue bag spotted near entrance",
      "score": 0.68,
      "metadata": {...}
    },
    // ... 6 more results (total 7 on last page)
  ],
  "pagination": {
    "page": 5,
    "page_size": 10,
    "total_results": 47,
    "total_pages": 5
  }
}
```
