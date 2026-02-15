# Design: Vector Search API Endpoint

## Status: PLANNED
## Date: 2026-02-14

---

## 1. Overview

Extend the existing Modal FastAPI application with a vector similarity search endpoint that queries the Elasticsearch RAG database. The endpoint receives a natural language query from the frontend, converts it to an embedding via Jina AI, performs kNN vector search in Elasticsearch, and returns the top 3 most similar observations as JSON formatted for the frontend table component.

### Goals

- Expose a new `POST /search` endpoint on the existing Modal app
- Convert user query text to a 1024-dim embedding via Jina AI (same model as ingestion)
- Perform kNN vector similarity search in Elasticsearch using cosine similarity
- Return the top 3 most similar documents with scores, content, and metadata
- Format response JSON to match frontend DataTableView requirements

---

## 2. Architecture

### 2.1 System Context

```
┌──────────────────┐   POST /search     ┌──────────────────────────────┐
│  Frontend UI     │───────────────────▶│  Modal App (FastAPI)         │
│  (React)         │                    │                              │
└──────────────────┘                    │  1. Validate JSON            │
                                        │  2. Extract query text       │
                                        │  3. Embed via Jina API       │
                                        │  4. kNN search in ES         │
                                        │  5. Format & return top 3    │
                                        └──────────┬───────────────────┘
                                                   │
                               ┌────────────────────┼────────────────────┐
                               ▼                                        ▼
                 ┌─────────────────────────┐          ┌─────────────────────────┐
                 │  Jina Embeddings API    │          │  Elasticsearch Cloud    │
                 │  (same as ingestion)    │          │  kNN vector search      │
                 │  model: jina-embed-v3   │          │  similarity: cosine     │
                 └─────────────────────────┘          └─────────────────────────┘
```

### 2.2 Integration with Existing System

| Existing Component | Integration Point | Reuse Strategy |
|-------------------|-------------------|----------------|
| **Jina Embeddings** (`embeddings.py`) | `get_embeddings()` function | Direct reuse — query uses same model/task as ingestion |
| **Elasticsearch Client** (`vectordb.py`) | `get_client()` function | Add new `search_similar()` function to vectordb.py |
| **Modal App** (`main.py`) | Add new FastAPI route | Mount alongside `/ingest`, `/ingest/batch`, `/health` |
| **Pydantic Models** (`models.py`) | Add new request/response schemas | Define `SearchRequest`, `SearchResult`, `SearchResponse` |
| **Frontend DataTable** | JSON response schema | Match expected `{ results: [{id, content, score, metadata}] }` format |

### 2.3 Embedding Consistency

**Critical**: Use the **same Jina model and task** for search queries as for ingestion to ensure vector space compatibility.

| Context | Model | Task | Dimensions |
|---------|-------|------|-----------|
| Ingestion (existing) | `jina-embeddings-v3` | `retrieval.passage` | 1024 |
| Search Query (new) | `jina-embeddings-v3` | `retrieval.query` | 1024 |

**Note**: Jina embeddings v3 supports asymmetric retrieval — use `retrieval.query` task for search queries and `retrieval.passage` task for documents (already implemented).

---

## 3. Input/Output Schema

### 3.1 Search Request

**Endpoint**: `POST /search`

**Request Body**:
```json
{
  "query": "A blue hardcover book was stolen from the library desk"
}
```

### 3.2 Search Response

**Response Body** (200 OK):
```json
{
  "query": "A blue hardcover book was stolen from the library desk",
  "results": [
    {
      "id": "es_doc_id_001",
      "content": "Blue hardcover book detected on shelf near entrance camera",
      "score": 0.92,
      "metadata": {
        "object": "book",
        "color": "blue",
        "timestamp": "2026-02-10T09:15:00Z",
        "motion_vector": [0.3, -0.1],
        "device_id": "jetson_01"
      }
    },
    {
      "id": "es_doc_id_002",
      "content": "Blue bag moved from table to floor area",
      "score": 0.78,
      "metadata": {
        "object": "bag",
        "color": "blue",
        "timestamp": "2026-02-11T14:30:00Z",
        "motion_vector": [0.5, -0.4],
        "device_id": "jetson_02"
      }
    },
    {
      "id": "es_doc_id_003",
      "content": "Person carrying blue item exiting through side door",
      "score": 0.65,
      "metadata": {
        "object": "unknown",
        "color": "blue",
        "timestamp": "2026-02-12T18:45:00Z",
        "motion_vector": [0.8, 0.2],
        "device_id": "jetson_03"
      }
    }
  ]
}
```

### 3.3 Field Contract

| Field | Type | Source | Purpose |
|-------|------|--------|---------|
| `query` | `string` | Request echo | Original user query for frontend reference |
| `results` | `array[SearchResult]` | Elasticsearch kNN | Top 3 most similar observations |
| `results[].id` | `string` | ES `_id` | Document identifier for detail view linking |
| `results[].content` | `string` | ES `content` field | Human-readable observation description |
| `results[].score` | `float (0-1)` | ES `_score` normalized | Cosine similarity score (1 = identical, 0 = orthogonal) |
| `results[].metadata` | `object` | ES `metadata` field | Original metadata from ingestion |

**Frontend Consumption**:
- **DataTableView**: Maps `content` → Content column, `metadata.timestamp` → Time column, `score * 100` → Likelihood % badge
- **CalendarView**: Groups by `metadata.timestamp` date, uses `score` for color tier (high/medium/low)

---

## 4. External Dependencies

### 4.1 Elasticsearch kNN Search (Python Client)

**Package**: `elasticsearch` (already installed, v8.17+)

**kNN Search API** (via `client.search()`):
```python
from elasticsearch import Elasticsearch

response = client.search(
    index="observations-v1",
    knn={
        "field": "embedding",
        "query_vector": [0.1, 0.2, ...],  # 1024-dim query embedding from Jina
        "k": 3,                           # Top 3 results
        "num_candidates": 100             # Consider 100 candidates (10-20x k is recommended)
    },
    _source=["content", "metadata"]      # Only return needed fields (exclude embedding)
)
```

**Key Parameters**:
- **`field`**: `"embedding"` (dense_vector field in ES index)
- **`query_vector`**: 1024-dim list of floats from Jina API
- **`k`**: Number of results to return (3 for this use case)
- **`num_candidates`**: Candidates to consider before selecting top k (higher = more accurate but slower)
- **`_source`**: Fields to return (exclude large embedding array to reduce response size)

**Response Structure**:
```python
{
    "hits": {
        "hits": [
            {
                "_id": "doc_001",
                "_score": 0.92,        # Cosine similarity score
                "_source": {
                    "content": "...",
                    "metadata": {...}
                }
            },
            # ... more results
        ]
    }
}
```

**Context7 Source**: `/elastic/elasticsearch-py` — official Elasticsearch Python client documentation confirms kNN search via `client.search()` with `knn` parameter.

### 4.2 Jina AI Embeddings (Asymmetric Retrieval)

**API Endpoint**: `https://api.jina.ai/v1/embeddings` (already configured in `config.py`)

**Task Parameter Optimization**:
| Use Case | Task | Embedding Focus |
|----------|------|-----------------|
| Ingestion (documents) | `retrieval.passage` | Optimize for document representation |
| Search (queries) | `retrieval.query` | Optimize for query representation |

**Query Embedding Call** (new):
```python
response = requests.post(
    JINA_API_URL,
    headers={
        "Authorization": f"Bearer {os.environ['JINA_API_KEY']}",
        "Content-Type": "application/json",
    },
    json={
        "model": "jina-embeddings-v3",
        "input": ["User query text here"],
        "task": "retrieval.query"  # Different from ingestion's "retrieval.passage"
    }
)
query_embedding = response.json()["data"][0]["embedding"]  # 1024-dim vector
```

**Why Asymmetric Tasks?**
Jina embeddings v3 is trained for asymmetric retrieval:
- **Queries** (short, intent-focused) → `retrieval.query`
- **Documents** (longer, content-focused) → `retrieval.passage`

This improves search relevance compared to using the same task for both.

---

## 5. Algorithm Design

### 5.1 Search Flow (Step-by-Step)

```
User Query (text)
    │
    ▼
1. Validate request (non-empty query string)
    │
    ▼
2. Embed query via Jina API (task="retrieval.query")
    │   → Returns: 1024-dim query vector
    ▼
3. kNN search in Elasticsearch
    │   field: "embedding"
    │   query_vector: [1024 floats]
    │   k: 3
    │   num_candidates: 100
    │   _source: ["content", "metadata"]
    ▼
4. Parse Elasticsearch response
    │   Extract: _id, _score, content, metadata
    ▼
5. Format as SearchResponse JSON
    │   results: [{ id, content, score, metadata }]
    ▼
Return to frontend (200 OK)
```

### 5.2 Score Normalization

**Elasticsearch Score**: Cosine similarity scores from ES are already normalized 0–1:
- **1.0** = Identical vectors (perfect match)
- **0.5** = Orthogonal vectors (no similarity)
- **0.0** = Opposite vectors (rare in practice)

**No transformation needed** — return scores as-is. Frontend will multiply by 100 for percentage display.

### 5.3 Result Ranking

Elasticsearch returns results **pre-sorted by score** (highest first), so:
- No additional sorting required in Python
- Top 3 results are guaranteed to be the most similar
- Ties are broken by ES internal document ordering (stable)

---

## 6. API Design

### 6.1 New Route in `main.py`

**Route**: `POST /search`

**Handler Pseudocode**:
```python
@web_app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    # 1. Validate
    if not req.query.strip():
        raise HTTPException(400, "query must be a non-empty string")

    # 2. Embed query
    query_embedding = get_query_embedding(req.query)  # New function

    # 3. kNN search
    es = _get_es()
    results = search_similar(es, query_embedding, k=3)  # New function in vectordb.py

    # 4. Format response
    return SearchResponse(
        query=req.query,
        results=[
            SearchResult(
                id=hit["_id"],
                content=hit["_source"]["content"],
                score=hit["_score"],
                metadata=Metadata(**hit["_source"]["metadata"])
            )
            for hit in results
        ]
    )
```

### 6.2 New Functions Required

**In `embeddings.py`**:
```python
def get_query_embedding(query: str) -> list[float]:
    """Embed a search query via Jina API using retrieval.query task."""
    # Similar to get_embeddings() but task="retrieval.query" and single text
```

**In `vectordb.py`**:
```python
def search_similar(
    client: Elasticsearch,
    query_vector: list[float],
    k: int = 3
) -> list[dict]:
    """kNN vector search. Returns top k most similar documents."""
    # Uses client.search() with knn parameter
```

**In `models.py`**:
```python
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

---

## 7. Performance Considerations

### 7.1 Latency Targets

| Component | Expected Latency | Notes |
|-----------|------------------|-------|
| Jina API embed call | 100-300ms | Single query embedding |
| ES kNN search | 50-200ms | Depends on index size, `num_candidates` |
| Modal cold start | 1-3s (first request only) | Container initialization |
| **Total (warm)** | **150-500ms** | Acceptable for interactive search |

### 7.2 Scalability

**Current Approach** (Sufficient for MVP):
- Single query embedding per request
- ES searches full index (`num_candidates=100`)
- No caching or pre-filtering

**Future Optimizations** (if needed):
- **Pre-filtering**: Add `filter` clauses to kNN search (e.g., filter by `metadata.device_id` or date range)
- **Caching**: Cache popular query embeddings (low hit rate expected for natural language queries)
- **Batch Search**: Support multiple queries in one request (not needed for current frontend)

### 7.3 Cost Analysis

| Service | Cost Driver | Estimated Cost (per 1000 requests) |
|---------|-------------|-----------------------------------|
| Jina API | Embedding requests | ~$0.02 (at $0.02/1M tokens, ~1K tokens/query) |
| Elasticsearch | Search operations | Included in serverless pricing (pay per compute) |
| Modal | Function invocations + compute | ~$0.01-0.05 (depending on region/concurrency) |
| **Total** | | **~$0.03-0.07 per 1000 searches** |

---

## 8. Error Handling

| Failure Scenario | HTTP Status | Response | Recovery Strategy |
|-----------------|-------------|----------|-------------------|
| Empty query string | 400 | `{"detail": "query must be a non-empty string"}` | Validation at FastAPI layer |
| Jina API timeout | 504 | `{"detail": "Embedding service timeout"}` | Retry once with exponential backoff |
| Jina API rate limit (429) | 429 | `{"detail": "Rate limit exceeded, retry after N seconds"}` | Return rate limit info to frontend |
| ES connection failure | 503 | `{"detail": "Search service unavailable"}` | Retry with backoff, log error |
| ES query timeout | 504 | `{"detail": "Search timeout"}` | Reduce `num_candidates` or add filtering |
| No results found | 200 | `{"query": "...", "results": []}` | Valid response — frontend shows "No matches found" |
| Invalid ES response | 500 | `{"detail": "Internal error"}` | Log full error, return generic message |

**Observability**:
- Log all search queries with latency metrics
- Track empty result rate (may indicate data quality issues)
- Monitor Jina API and ES error rates
- Alert on p95 latency > 1s

---

## 9. Security Considerations

### 9.1 Input Validation

- **Query Length Limit**: Max 1000 characters (prevent abuse of Jina API)
- **Rate Limiting**: 10 requests/minute per IP (future enhancement)
- **Sanitization**: No SQL/NoSQL injection risk (ES query uses JSON, not string interpolation)

### 9.2 Data Exposure

- **Embedding Exclusion**: Never return the 1024-dim embedding array to frontend (large, not useful)
- **Metadata Filtering**: Current design returns all metadata fields — consider filtering sensitive fields in production
- **Document IDs**: ES `_id` values are exposed — ensure they're not guessable/sensitive

### 9.3 API Key Protection

- Jina and ES API keys remain in Modal secrets (not exposed to frontend)
- Frontend never has direct access to vector database

---

## 10. Testing Strategy

### 10.1 Unit Tests

| Test Case | Input | Expected Output |
|-----------|-------|-----------------|
| Valid query | `{"query": "blue book"}` | 200, `results` array with ≤3 items |
| Empty query | `{"query": ""}` | 400, error message |
| Query with no matches | `{"query": "xyzabc123nonsense"}` | 200, `results: []` |
| Special characters | `{"query": "book @ library?!"}` | 200, valid results |
| Very long query | `{"query": "..." * 1000}` | 400, "query too long" error |

### 10.2 Integration Tests

1. **End-to-End Search Flow**:
   - Ingest sample observation: `POST /ingest` with `content="Blue backpack on desk"`
   - Wait for ES index refresh (1s)
   - Search: `POST /search` with `query="blue bag"`
   - Assert: Top result contains "Blue backpack" with `score > 0.7`

2. **Score Verification**:
   - Ingest identical document twice with different IDs
   - Search with exact match query
   - Assert: Top result has `score ≈ 1.0`

3. **Result Ordering**:
   - Ingest 5 documents with varying similarity to query
   - Search and verify results are sorted by score (descending)

### 10.3 Manual Testing

**Health Check**:
```bash
curl https://alemanb--treehacks-vector-search-web.modal.run/health
# Expected: {"status": "ok", "elasticsearch": "connected", "jina": "reachable"}
```

**Sample Search**:
```bash
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/search \
  -H "Content-Type: application/json" \
  -d '{"query": "blue book stolen from library"}'
# Expected: 200, JSON with top 3 results
```

---

## 11. Implementation Phases

### Phase 1: Core Search Function
1. Add `get_query_embedding()` to `embeddings.py`
2. Add `search_similar()` to `vectordb.py`
3. Add Pydantic models to `models.py` (`SearchRequest`, `SearchResult`, `SearchResponse`)

### Phase 2: API Route
4. Add `POST /search` route to `main.py`
5. Wire up validation, embedding, search, response formatting

### Phase 3: Testing & Validation
6. Deploy to Modal (`modal deploy main.py`)
7. Run manual integration tests with curl
8. Verify frontend integration with mock data replacement

### Phase 4: Optimization (Future)
9. Add query caching if needed
10. Implement rate limiting
11. Add pre-filtering support for metadata fields

---

## 12. Deployment

**No new deployment steps required** — the `/search` endpoint will be added to the existing Modal app:

```bash
# From modal/ directory
modal deploy main.py
```

**New URL**: `https://alemanb--treehacks-vector-search-web.modal.run/search`

**Frontend Integration Point**:
- Replace mock data in `src/hooks/useSearch.ts` with actual API call
- Update `BACKEND_URL` constant to point to Modal URL
- Test with real data from Elasticsearch

---

## 13. Success Criteria

| Metric | Target | Validation Method |
|--------|--------|-------------------|
| API Response Time | p95 < 1s | Load test with 100 concurrent requests |
| Search Accuracy | Top 3 results relevant to query in >80% of cases | Manual review of 50 diverse queries |
| Error Rate | <1% | Monitor production logs for 1 week |
| Empty Result Rate | <20% | Track searches with zero results |
| Frontend Integration | DataTable and Calendar render correctly | QA testing on staging frontend |

---

## 14. Future Enhancements

### 14.1 Filtering & Refinement
- **Metadata Filters**: Allow frontend to filter by `object`, `color`, `device_id`, date range
- **Hybrid Search**: Combine vector search with keyword matching for more precise results

### 14.2 Advanced Features
- **Explain Score**: Return why each result matched (highlight matching keywords/concepts)
- **Pagination**: Support `offset` and `limit` for >3 results
- **Aggregations**: Return facets (e.g., "5 books, 3 bags, 2 laptops")

### 14.3 Performance
- **Query Rewriting**: Use LLM to expand/rephrase ambiguous queries
- **Pre-computed Clusters**: Group similar observations for faster filtering
- **Index Optimization**: Tune ES index settings (`number_of_shards`, `refresh_interval`)

---

## 15. Key Design Decisions

### 15.1 Why Top 3 Only?
- **Frontend Constraint**: DataTable is designed for focused results, not pagination
- **User Experience**: More results = cognitive overload; 3 is a good balance
- **Performance**: Smaller k → faster ES response times

### 15.2 Why `num_candidates=100`?
- **Accuracy vs. Speed**: 100 candidates balances search quality with latency
- **Elasticsearch Recommendation**: 10-20x k is optimal (3 * 10 = 30, but 100 is safer for diverse queries)
- **Can be tuned**: Increase for better recall, decrease for faster searches

### 15.3 Why Asymmetric Retrieval Tasks?
- **Jina v3 Design**: Model is trained specifically for asymmetric retrieval
- **Better Relevance**: `retrieval.query` embeddings are optimized for search intent
- **Minimal Code Change**: Only task parameter differs from ingestion

### 15.4 Why Exclude Embedding from Response?
- **Size**: 1024 floats = ~8KB per result → 24KB overhead for 3 results
- **Usability**: Frontend doesn't need raw embeddings
- **Privacy**: Embeddings encode semantic meaning — no need to expose

---

## 16. Dependencies Summary

### New Code Required
| File | Changes |
|------|---------|
| `embeddings.py` | Add `get_query_embedding()` function |
| `vectordb.py` | Add `search_similar()` function |
| `models.py` | Add `SearchRequest`, `SearchResult`, `SearchResponse` models |
| `main.py` | Add `POST /search` route |

### External Dependencies
| Dependency | Status | Purpose |
|------------|--------|---------|
| `elasticsearch>=8.17` | Already installed | kNN search via `client.search()` |
| `requests>=2.31` | Already installed | Jina API calls |
| `fastapi[standard]` | Already installed | API framework |
| `modal` | Already installed | Serverless deployment |

**No new dependencies required** — all packages already installed for ingestion pipeline.

---

## 17. Context7 References

### Elasticsearch kNN Search
- **Library**: `/elastic/elasticsearch-py`
- **Key API**: `client.search(knn={...})`
- **Documentation**: https://github.com/elastic/elasticsearch-py/blob/main/docs/reference/dsl_how_to_guides.md

### Jina Embeddings v3
- **API**: `https://api.jina.ai/v1/embeddings`
- **Model**: `jina-embeddings-v3`
- **Tasks**: `retrieval.query` (search), `retrieval.passage` (ingestion)
- **Dimensions**: 1024

---

## Appendix A: Example Interaction

**Frontend Request**:
```http
POST /search HTTP/1.1
Host: alemanb--treehacks-vector-search-web.modal.run
Content-Type: application/json

{
  "query": "My blue backpack was stolen from the library"
}
```

**Backend Processing**:
1. Validate query (non-empty ✓)
2. Embed via Jina: `task="retrieval.query"` → `[0.023, -0.156, ..., 0.089]` (1024 dims)
3. ES kNN search: `field="embedding", k=3, num_candidates=100`
4. Parse results: 3 hits with scores [0.91, 0.84, 0.72]
5. Format response

**Frontend Response**:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "query": "My blue backpack was stolen from the library",
  "results": [
    {
      "id": "abc123",
      "content": "Blue backpack detected on shelf near entrance",
      "score": 0.91,
      "metadata": {
        "object": "backpack",
        "color": "blue",
        "timestamp": "2026-02-10T09:15:00Z",
        "device_id": "jetson_01"
      }
    },
    {
      "id": "def456",
      "content": "Blue bag moved from table to floor",
      "score": 0.84,
      "metadata": {
        "object": "bag",
        "color": "blue",
        "timestamp": "2026-02-11T14:30:00Z",
        "device_id": "jetson_02"
      }
    },
    {
      "id": "ghi789",
      "content": "Person carrying blue item exiting door",
      "score": 0.72,
      "metadata": {
        "object": "unknown",
        "color": "blue",
        "timestamp": "2026-02-12T18:45:00Z",
        "device_id": "jetson_03"
      }
    }
  ]
}
```

**Frontend Consumption**:
- **DataTableView**: Renders 3 rows with Content, Time, Likelihood (91%, 84%, 72%), and View links
- **CalendarView**: Highlights Feb 10, 11, 12 with color tiers (high, high, medium)
