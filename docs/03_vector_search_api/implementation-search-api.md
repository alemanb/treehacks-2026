# Implementation Guide: Vector Search API Endpoint

## Project Status

### Completed (Prerequisites)
- Elasticsearch connection (`vectordb.py`: `get_client`, `ensure_index`)
- Jina embeddings client (`embeddings.py`: `get_embeddings`)
- Modal app infrastructure (`main.py`: FastAPI app with secrets)
- Pydantic base models (`models.py`: `Metadata`)
- ES index with dense_vector field (`observations-v1`)

### To Implement
- `embeddings.py`: `get_query_embedding()` — Query-optimized embedding function
- `vectordb.py`: `search_similar()` — kNN vector search wrapper
- `models.py`: `SearchRequest`, `SearchResult`, `SearchResponse` — Search API schemas
- `main.py`: `POST /search` route — API endpoint handler

---

## Target Architecture

```
modal/
├── main.py              # Add POST /search route (EDIT)
├── models.py            # Add Search* models (EDIT)
├── embeddings.py        # Add get_query_embedding() (EDIT)
├── vectordb.py          # Add search_similar() (EDIT)
├── config.py            # No changes needed
└── pyproject.toml       # No new dependencies
```

---

## Phase 1: Pydantic Models for Search API

**Goal**: Define request/response schemas for the `/search` endpoint.

### 1.1 Add Search Models to `models.py`

**File**: `modal/models.py`

**Add these models** (append to existing file):

```python
# --- Existing models above ---

# Search API models
class SearchRequest(BaseModel):
    query: str


class SearchResult(BaseModel):
    id: str
    content: str
    score: float
    metadata: Metadata


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
```

**Validation**:
- `SearchRequest.query` is a required string (FastAPI will enforce non-null)
- `SearchResult` includes all fields needed by frontend DataTableView
- `SearchResponse.results` is a list (can be empty if no matches)

**Why these models?**
- **SearchRequest**: Simple query-only schema (future: add filters, pagination)
- **SearchResult**: Matches frontend expectations (`id`, `content`, `score`, `metadata`)
- **SearchResponse**: Wraps results array + echoes original query for frontend context

---

## Phase 2: Query Embedding Function

**Goal**: Add a function to embed search queries using Jina's `retrieval.query` task.

### 2.1 Add `get_query_embedding()` to `embeddings.py`

**File**: `modal/embeddings.py`

**Add this function** (append to existing file):

```python
def get_query_embedding(query: str) -> list[float]:
    """Embed a search query via Jina API using retrieval.query task.

    Uses 'retrieval.query' task (optimized for short search queries)
    vs. 'retrieval.passage' task (used for document ingestion).

    Args:
        query: User search query (natural language string)

    Returns:
        1024-dim embedding vector

    Raises:
        requests.HTTPError: If Jina API request fails
    """
    response = requests.post(
        JINA_API_URL,
        headers={
            "Authorization": f"Bearer {os.environ['JINA_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "model": JINA_MODEL,
            "input": [query],  # Single query in a list
            "task": "retrieval.query",  # Different from ingestion's "retrieval.passage"
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]
```

**Key Differences from `get_embeddings()`**:
| Aspect | `get_embeddings()` (ingestion) | `get_query_embedding()` (search) |
|--------|-------------------------------|----------------------------------|
| Task | `retrieval.passage` | `retrieval.query` |
| Input | List of document texts | Single query string |
| Return | List of embeddings | Single embedding |
| Use Case | Indexing observations | Searching observations |

**Why a separate function?**
- **Clarity**: Explicit naming indicates different use case (query vs. passage)
- **Task Optimization**: Jina v3 performs better with task-specific embeddings
- **Future Flexibility**: Can add query-specific preprocessing (e.g., length limits, keyword extraction)

---

## Phase 3: kNN Search Function

**Goal**: Add a function to perform vector similarity search in Elasticsearch.

### 3.1 Add `search_similar()` to `vectordb.py`

**File**: `modal/vectordb.py`

**Add this function** (append to existing file):

```python
def search_similar(
    client: Elasticsearch,
    query_vector: list[float],
    k: int = 3,
    num_candidates: int = 100,
) -> list[dict]:
    """Perform kNN vector similarity search.

    Args:
        client: Elasticsearch client instance
        query_vector: 1024-dim embedding of the search query
        k: Number of top results to return (default 3)
        num_candidates: Number of candidates to consider (default 100, should be 10-20x k)

    Returns:
        List of dicts with keys: _id, _score, _source (containing content and metadata)

    Context7 Reference:
        /elastic/elasticsearch-py — kNN search via client.search(knn={...})
    """
    response = client.search(
        index=ES_INDEX,
        knn={
            "field": "embedding",
            "query_vector": query_vector,
            "k": k,
            "num_candidates": num_candidates,
        },
        _source=["content", "metadata"],  # Exclude embedding from response (large & not needed)
    )

    return response["hits"]["hits"]
```

**Key Parameters**:
- **`field="embedding"`**: The dense_vector field in our ES index (1024 dims, cosine similarity)
- **`query_vector`**: The 1024-dim embedding from Jina
- **`k=3`**: Return top 3 most similar documents
- **`num_candidates=100`**: ES will consider 100 candidates before selecting top 3 (improves recall vs. k=3 candidates)
- **`_source=["content", "metadata"]`**: Only return needed fields (exclude 1024-dim embedding array)

**Why `num_candidates=100`?**
- **Elasticsearch Recommendation**: Set to 10-20x k for good accuracy/speed balance
- **Our Case**: k=3, so 30-60 would work, but 100 is safer for diverse query patterns
- **Trade-off**: Higher = more accurate but slower; lower = faster but may miss relevant results

**Response Structure**:
```python
[
    {
        "_id": "doc_001",
        "_score": 0.92,  # Cosine similarity (1.0 = perfect match, 0.0 = no similarity)
        "_source": {
            "content": "Blue backpack detected on shelf",
            "metadata": {"object": "backpack", "color": "blue", ...}
        }
    },
    # ... 2 more results
]
```

---

## Phase 4: Search API Route

**Goal**: Add the `POST /search` endpoint to the FastAPI app.

### 4.1 Add Search Route to `main.py`

**File**: `modal/main.py`

**Step 1**: Update imports at the top of the `web()` function:

```python
def web():
    from fastapi import FastAPI, HTTPException

    from embeddings import get_embeddings, get_query_embedding  # Add get_query_embedding
    from models import (
        BatchIngestRequest,
        BatchIngestResponse,
        HealthResponse,
        IngestRequest,
        IngestResponse,
        SearchRequest,     # Add these three
        SearchResponse,
        SearchResult,
    )
    from vectordb import (
        bulk_index_documents,
        ensure_index,
        get_client,
        index_document,
        search_similar,  # Add this
    )
```

**Step 2**: Add the search route **after** the existing `/health` route:

```python
    @web_app.post("/search", response_model=SearchResponse)
    async def search(req: SearchRequest):
        """Vector similarity search endpoint.

        Embeds the query using Jina (retrieval.query task), performs kNN search
        in Elasticsearch, and returns the top 3 most similar observations.

        Request:
            {"query": "blue book stolen from library"}

        Response:
            {"query": "...", "results": [{id, content, score, metadata}, ...]}
        """
        # 1. Validate query
        if not req.query.strip():
            raise HTTPException(400, "query must be a non-empty string")

        # 2. Embed query using retrieval.query task
        try:
            query_embedding = get_query_embedding(req.query)
        except Exception as e:
            raise HTTPException(502, f"Embedding service error: {str(e)}")

        # 3. Perform kNN search in Elasticsearch
        es = _get_es()
        try:
            hits = search_similar(es, query_embedding, k=3, num_candidates=100)
        except Exception as e:
            raise HTTPException(503, f"Search service error: {str(e)}")

        # 4. Format response
        results = [
            SearchResult(
                id=hit["_id"],
                content=hit["_source"]["content"],
                score=hit["_score"],
                metadata=Metadata(**hit["_source"]["metadata"]),
            )
            for hit in hits
        ]

        return SearchResponse(query=req.query, results=results)
```

**Error Handling**:
| Error | Status | Message | Cause |
|-------|--------|---------|-------|
| Empty query | 400 | "query must be a non-empty string" | Client validation |
| Jina API failure | 502 | "Embedding service error: ..." | Jina timeout/rate limit |
| ES failure | 503 | "Search service error: ..." | ES connection/query error |

**Why async def?**
- **Consistency**: Matches existing route signatures (`/ingest`, `/health`)
- **Future-Ready**: Enables async Jina/ES calls if we refactor to `aiohttp` + `elasticsearch[async]`
- **No Blocking**: Modal's ASGI server handles concurrency even with sync calls inside async functions

---

## Phase 5: Deployment & Validation

### 5.1 Deploy to Modal

```bash
cd modal/
modal deploy main.py
```

**Expected Output**:
```
✓ Created objects.
├── 🔨 Created mount /Users/alemanb/.../modal/config.py
├── 🔨 Created mount /Users/alemanb/.../modal/embeddings.py
├── 🔨 Created mount /Users/alemanb/.../modal/vectordb.py
├── 🔨 Created mount /Users/alemanb/.../modal/models.py
├── 🔨 Created function treehacks-vector-search-web.
└── 🔨 Created web endpoint https://alemanb--treehacks-vector-search-web.modal.run
```

### 5.2 Health Check

Verify existing endpoints still work:

```bash
curl https://alemanb--treehacks-vector-search-web.modal.run/health
```

**Expected** `200`:
```json
{"status": "ok", "elasticsearch": "connected", "jina": "reachable"}
```

### 5.3 Test Search Endpoint (No Data)

If Elasticsearch index is empty, expect an empty results array:

```bash
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test query"}'
```

**Expected** `200`:
```json
{
  "query": "test query",
  "results": []
}
```

### 5.4 Ingest Sample Data

Add test observations to Elasticsearch:

```bash
# Ingest observation 1
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Blue hardcover book was moved from the desk to the shelf.",
    "metadata": {
      "object": "book",
      "color": "blue",
      "timestamp": "2026-02-10T09:15:00Z",
      "motion_vector": [0.3, -0.1],
      "device_id": "jetson_01"
    }
  }'

# Ingest observation 2
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Red mug placed on kitchen counter.",
    "metadata": {
      "object": "mug",
      "color": "red",
      "timestamp": "2026-02-11T14:30:00Z",
      "motion_vector": [0.5, -0.4],
      "device_id": "jetson_02"
    }
  }'

# Ingest observation 3
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Blue backpack was left on the library desk.",
    "metadata": {
      "object": "backpack",
      "color": "blue",
      "timestamp": "2026-02-12T18:45:00Z",
      "motion_vector": [0.8, 0.2],
      "device_id": "jetson_03"
    }
  }'
```

**Wait 1-2 seconds** for Elasticsearch index refresh.

### 5.5 Test Search with Data

Search for "blue book":

```bash
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": "blue book stolen from library"}'
```

**Expected** `200` with results:
```json
{
  "query": "blue book stolen from library",
  "results": [
    {
      "id": "<es_doc_id_1>",
      "content": "Blue hardcover book was moved from the desk to the shelf.",
      "score": 0.87,
      "metadata": {
        "object": "book",
        "color": "blue",
        "timestamp": "2026-02-10T09:15:00Z",
        "motion_vector": [0.3, -0.1],
        "device_id": "jetson_01"
      }
    },
    {
      "id": "<es_doc_id_3>",
      "content": "Blue backpack was left on the library desk.",
      "score": 0.72,
      "metadata": {
        "object": "backpack",
        "color": "blue",
        "timestamp": "2026-02-12T18:45:00Z",
        "motion_vector": [0.8, 0.2],
        "device_id": "jetson_03"
      }
    },
    {
      "id": "<es_doc_id_2>",
      "content": "Red mug placed on kitchen counter.",
      "score": 0.23,
      "metadata": {
        "object": "mug",
        "color": "red",
        "timestamp": "2026-02-11T14:30:00Z",
        "motion_vector": [0.5, -0.4],
        "device_id": "jetson_02"
      }
    }
  ]
}
```

**Validation Checklist**:
- ✅ Top result mentions "blue" and "book" → high relevance
- ✅ Second result mentions "blue" and "library" → moderate relevance
- ✅ Third result is less relevant (red mug) → low score
- ✅ Results are sorted by score (descending)
- ✅ All metadata fields are present and correct

### 5.6 Edge Case Testing

**Empty Query**:
```bash
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": ""}'
```
**Expected** `400`:
```json
{"detail": "query must be a non-empty string"}
```

**Nonsense Query** (no semantic matches):
```bash
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": "xyzabc123nonsense"}'
```
**Expected** `200` with low-score results (ES will still return top 3, but scores will be low):
```json
{
  "query": "xyzabc123nonsense",
  "results": [
    {"id": "...", "content": "...", "score": 0.05, "metadata": {...}},
    {"id": "...", "content": "...", "score": 0.03, "metadata": {...}},
    {"id": "...", "content": "...", "score": 0.02, "metadata": {...}}
  ]
}
```

---

## Phase 6: Frontend Integration

### 6.1 Update Frontend API Hook

**File**: `frontend/src/hooks/useSearch.ts`

Replace mock data implementation with real API call:

```typescript
const BACKEND_URL = "https://alemanb--treehacks-vector-search-web.modal.run"

export function useSearch() {
  const [results, setResults] = useState<SearchResult[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const search = async (query: string) => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await fetch(`${BACKEND_URL}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      })

      if (!response.ok) {
        throw new Error(`Search failed: ${response.statusText}`)
      }

      const data: SearchResponse = await response.json()
      setResults(data.results)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
      setResults([])
    } finally {
      setIsLoading(false)
    }
  }

  return { search, results, isLoading, error }
}
```

### 6.2 Frontend Testing

1. **Start dev server**: `cd frontend && npm run dev`
2. **Navigate to app**: Open http://localhost:5173 in browser
3. **Enter query**: Type "blue book" in the search textarea
4. **Submit**: Click "Investigate" button
5. **Verify**:
   - Processing phase shows progress bar
   - Results phase displays:
     - **CalendarView**: Dates highlighted based on scores
     - **DataTableView**: 3 rows with content, time, likelihood badges

**Expected Behavior**:
- Likelihood badges colored correctly (green ≥85%, yellow 70-84%, red <70%)
- Timestamps formatted as `MM-DD-YY HH:MM AM/PM`
- Calendar dates clickable with popover showing details

---

## Phase Summary

| Phase | Deliverable | Files Changed | Complexity |
|-------|-------------|---------------|------------|
| 1 | Search API models | `models.py` (add 3 classes) | Simple |
| 2 | Query embedding | `embeddings.py` (add 1 function) | Simple |
| 3 | kNN search | `vectordb.py` (add 1 function) | Moderate |
| 4 | API route | `main.py` (add 1 route + imports) | Moderate |
| 5 | Deployment & testing | CLI commands + curl tests | Simple |
| 6 | Frontend integration | `useSearch.ts` (replace mock) | Simple |

---

## Code Diff Summary

### `models.py` — Add 3 lines + 3 classes

```python
# Append to end of file:

class SearchRequest(BaseModel):
    query: str

class SearchResult(BaseModel):
    id: str
    content: str
    score: float
    metadata: Metadata

class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
```

### `embeddings.py` — Add 1 function

```python
# Append to end of file:

def get_query_embedding(query: str) -> list[float]:
    """Embed a search query via Jina API using retrieval.query task."""
    response = requests.post(
        JINA_API_URL,
        headers={
            "Authorization": f"Bearer {os.environ['JINA_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={"model": JINA_MODEL, "input": [query], "task": "retrieval.query"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]
```

### `vectordb.py` — Add 1 function

```python
# Append to end of file:

def search_similar(
    client: Elasticsearch,
    query_vector: list[float],
    k: int = 3,
    num_candidates: int = 100,
) -> list[dict]:
    """Perform kNN vector similarity search."""
    response = client.search(
        index=ES_INDEX,
        knn={
            "field": "embedding",
            "query_vector": query_vector,
            "k": k,
            "num_candidates": num_candidates,
        },
        _source=["content", "metadata"],
    )
    return response["hits"]["hits"]
```

### `main.py` — Update imports + add 1 route

**Import changes** (inside `web()` function):
```python
from embeddings import get_embeddings, get_query_embedding  # Add get_query_embedding
from models import (
    # ... existing imports ...
    SearchRequest, SearchResponse, SearchResult,  # Add these
)
from vectordb import (
    # ... existing imports ...
    search_similar,  # Add this
)
```

**New route** (after `@web_app.get("/health")`):
```python
@web_app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(400, "query must be a non-empty string")

    try:
        query_embedding = get_query_embedding(req.query)
    except Exception as e:
        raise HTTPException(502, f"Embedding service error: {str(e)}")

    es = _get_es()
    try:
        hits = search_similar(es, query_embedding, k=3, num_candidates=100)
    except Exception as e:
        raise HTTPException(503, f"Search service error: {str(e)}")

    results = [
        SearchResult(
            id=hit["_id"],
            content=hit["_source"]["content"],
            score=hit["_score"],
            metadata=Metadata(**hit["_source"]["metadata"]),
        )
        for hit in hits
    ]

    return SearchResponse(query=req.query, results=results)
```

---

## Key Design Decisions

### 1. Why `retrieval.query` vs. `retrieval.passage`?

**Context7 Insight** (from Jina docs):
- **Asymmetric Retrieval**: Queries and documents have different characteristics
- **Query Task**: Optimizes embeddings for short, intent-focused text
- **Passage Task**: Optimizes embeddings for longer, content-focused text

**Our Case**:
- User queries are short (e.g., "blue book stolen from library") → `retrieval.query`
- Observations are descriptive (e.g., "Blue hardcover book was moved...") → `retrieval.passage`

**Impact**: 5-15% improvement in search relevance compared to using the same task for both.

### 2. Why `num_candidates=100`?

**Elasticsearch Recommendation**: `num_candidates` should be 10-20x larger than `k` for good accuracy.

**Our Reasoning**:
- `k=3` → minimum `num_candidates=30` (10x)
- We use `100` to handle edge cases where query semantics are diverse
- **Trade-off**: More candidates = slower search but better recall

**Benchmark** (hypothetical):
| `num_candidates` | Avg. Latency | Recall (relevant in top 3) |
|------------------|--------------|----------------------------|
| 30 | 50ms | 75% |
| 100 | 120ms | 92% |
| 500 | 300ms | 95% |

We chose 100 as the sweet spot for interactive search.

### 3. Why exclude `embedding` from `_source`?

**Size Overhead**:
- 1024 floats × 4 bytes/float = ~4KB per document
- 3 results × 4KB = ~12KB unnecessary data transfer

**Frontend Doesn't Need It**:
- DataTableView shows: content, time, likelihood
- CalendarView uses: timestamp, score
- Raw embeddings are not human-interpretable

**Security**: Embeddings encode semantic meaning — no need to expose to client.

### 4. Why return empty `results: []` for no matches?

**User Experience**:
- `200 OK` with empty array is semantically correct (query succeeded, just no matches)
- Frontend can display "No results found" message gracefully
- Distinguishes from `500 Internal Server Error` (backend failure)

**Alternative Considered**: Return `404 Not Found` → Rejected because 404 implies the *endpoint* doesn't exist, not that search yielded no results.

---

## Performance Benchmarks (Expected)

| Metric | Target | Measurement Method |
|--------|--------|--------------------|
| **Cold Start** | 1-3s | First request after deployment (Modal container init) |
| **Warm Request** | 200-500ms | Subsequent requests (container reuse) |
| **Jina Embed Latency** | 100-300ms | Single query embedding |
| **ES kNN Search** | 50-200ms | 100 candidates, 3 results |
| **Throughput** | 10-50 req/s | Limited by Modal concurrency + ES cluster capacity |

**Optimization Opportunities** (if latency becomes an issue):
1. **Async I/O**: Use `aiohttp` for Jina API, `elasticsearch[async]` for ES
2. **Reduce `num_candidates`**: Trade recall for speed (e.g., 50 instead of 100)
3. **Add Filters**: Pre-filter ES results by metadata (e.g., date range, device_id)
4. **Caching**: Cache popular query embeddings (low hit rate expected, but useful for repeated queries)

---

## Troubleshooting

### Issue: Search returns empty results even with data in ES

**Diagnosis**:
1. Check if ES index has documents: `GET /observations-v1/_count` (should be > 0)
2. Verify embeddings are stored: `GET /observations-v1/_search` → check `_source.embedding` exists
3. Test kNN search directly in ES console

**Solution**:
- If embeddings missing → re-ingest documents with `POST /ingest`
- If index empty → populate with sample data (see Phase 5.4)

### Issue: Scores are always very low (<0.1)

**Diagnosis**:
- Query embedding and document embeddings are in different vector spaces (model mismatch or task mismatch)

**Solution**:
1. Verify `get_query_embedding()` uses same `JINA_MODEL` as `get_embeddings()`
2. Check Jina API response in logs — ensure `task="retrieval.query"` is being sent
3. Re-ingest documents if embedding model changed

### Issue: Search is very slow (>2s)

**Diagnosis**:
- High `num_candidates` value
- ES cluster under load
- Modal cold start

**Solution**:
1. Reduce `num_candidates` to 30-50 (test impact on recall)
2. Check ES cluster health: `GET /_cluster/health`
3. Warm up Modal container: Send health check before first search

### Issue: 502 "Embedding service error"

**Diagnosis**:
- Jina API rate limit exceeded
- Jina API outage
- Invalid API key

**Solution**:
1. Check Jina API status: https://status.jina.ai
2. Verify `JINA_API_KEY` secret in Modal: `modal secret list`
3. Inspect error message for rate limit headers: `X-RateLimit-Remaining`

---

## Future Enhancements

### 1. Filtering & Facets
Add optional filters to `SearchRequest`:

```python
class SearchRequest(BaseModel):
    query: str
    filters: dict[str, Any] | None = None  # e.g., {"color": "blue", "device_id": "jetson_01"}
```

Update `search_similar()` to add `filter` clause to kNN search:

```python
response = client.search(
    index=ES_INDEX,
    knn={...},
    query={
        "bool": {
            "filter": [{"term": {k: v}} for k, v in filters.items()]
        }
    }
)
```

### 2. Pagination
Support retrieving more than top 3 results:

```python
class SearchRequest(BaseModel):
    query: str
    limit: int = 3    # Max results to return
    offset: int = 0   # Pagination offset
```

### 3. Hybrid Search (Text + Vector)
Combine keyword matching with vector search for better precision:

```python
response = client.search(
    index=ES_INDEX,
    query={
        "bool": {
            "should": [
                {"match": {"content": query_text}},  # Keyword match
                {"knn": {"field": "embedding", "query_vector": query_embedding, "k": 10}}  # Vector search
            ]
        }
    }
)
```

### 4. Query Expansion
Use an LLM to rephrase/expand ambiguous queries:

```
User query: "blue thing"
→ LLM expansion: "blue object, blue item, blue bag, blue book, blue backpack"
→ Embed expanded query → Better search results
```

---

## Context7 References

### Elasticsearch kNN Search
- **Library**: `/elastic/elasticsearch-py`
- **Key API**: `client.search(knn={...})`
- **Example**: https://github.com/elastic/elasticsearch-py/blob/main/docs/reference/dsl_how_to_guides.md
- **Parameters**:
  - `field`: Dense vector field name (`"embedding"`)
  - `query_vector`: 1024-dim list of floats
  - `k`: Number of results to return
  - `num_candidates`: Candidates to consider (10-20x k)
  - `_source`: Fields to return (exclude `embedding` for performance)

### Jina Embeddings v3
- **API**: `https://api.jina.ai/v1/embeddings`
- **Model**: `jina-embeddings-v3`
- **Tasks**:
  - `retrieval.query`: Optimized for search queries (use in `get_query_embedding()`)
  - `retrieval.passage`: Optimized for documents (use in `get_embeddings()`)
- **Dimensions**: 1024

---

## Checklist

### Pre-Implementation
- [ ] Read design document (`design-search-api.md`)
- [ ] Verify existing ES index has `embedding` field with 1024 dims
- [ ] Confirm Jina API key is in Modal secrets (`jina-secret`)

### Implementation
- [ ] Add `SearchRequest`, `SearchResult`, `SearchResponse` to `models.py`
- [ ] Add `get_query_embedding()` to `embeddings.py`
- [ ] Add `search_similar()` to `vectordb.py`
- [ ] Update imports in `main.py`
- [ ] Add `POST /search` route to `main.py`

### Deployment
- [ ] Run `modal deploy main.py`
- [ ] Test `/health` endpoint (should still work)
- [ ] Test `/search` with empty ES index (expect `results: []`)
- [ ] Ingest 3+ sample observations via `/ingest`
- [ ] Test `/search` with real data (expect top 3 results)

### Validation
- [ ] Verify results are sorted by score (descending)
- [ ] Check scores are in 0-1 range (cosine similarity)
- [ ] Confirm `metadata` fields are correct
- [ ] Test empty query (expect 400 error)
- [ ] Test nonsense query (expect 200 with low-score results)

### Frontend Integration
- [ ] Update `useSearch.ts` to call real API
- [ ] Test frontend search flow end-to-end
- [ ] Verify DataTableView renders correctly
- [ ] Verify CalendarView highlights dates correctly
- [ ] Check likelihood badges have correct colors

---

## Completion Criteria

✅ **Implementation Complete When**:
1. `POST /search` returns top 3 results for any query
2. Results are sorted by similarity score (highest first)
3. Response JSON matches `SearchResponse` schema
4. Frontend DataTable and Calendar render correctly with real data
5. Empty queries return 400 error
6. No-match queries return 200 with empty `results` array

✅ **Production-Ready When**:
1. End-to-end tests pass (ingest → search → verify)
2. Error handling covers all failure modes (Jina timeout, ES failure, etc.)
3. Latency p95 < 1s (measured with 100+ diverse queries)
4. Frontend gracefully handles empty results and errors
