# Implementation Guide: Vector Search Pipeline

## Project Status

### Completed
- `config.py` — Constants (ES endpoint, Jina model, dimensions)
- `embeddings.py` — Jina embeddings client (`get_embeddings`)
- `vectordb.py` — Elasticsearch client (`get_client`, `ensure_index`, `index_document`)
- `pyproject.toml` — Dependencies defined (`elasticsearch>=8.17`, `fastapi[standard]`, `modal`, `requests>=2.31`)
- `.env` — Local secrets file (gitignored)

### Missing
- `main.py` — Modal app + FastAPI routes (the entire API layer)
- `models.py` — Pydantic request/response schemas
- Modal secrets creation (`jina-secret`, `elastic-secret`)
- Bulk indexing support in `vectordb.py`
- Deployment + validation

---

## Target File Structure

```
modal/
├── main.py              # Modal app definition + FastAPI ASGI entrypoint
├── models.py            # Pydantic schemas (request/response)
├── embeddings.py        # Jina embeddings client (DONE)
├── vectordb.py          # Elasticsearch operations (PARTIAL — needs bulk)
├── config.py            # Constants (DONE)
├── pyproject.toml       # Dependencies (DONE)
├── .env                 # Local secrets (DONE, gitignored)
└── README.md            # Usage and deployment instructions
```

---

## Phase 1: Pydantic Models (`models.py`)

**Goal**: Extract request/response schemas into a dedicated file for clarity and reuse.

**Create `modal/models.py`**:

```python
from pydantic import BaseModel


class Metadata(BaseModel):
    object: str | None = None
    color: str | None = None
    timestamp: str | None = None
    motion_vector: list[float] | None = None
    device_id: str | None = None


class IngestRequest(BaseModel):
    content: str
    metadata: Metadata | None = None


class BatchIngestRequest(BaseModel):
    documents: list[IngestRequest]


class IngestResponse(BaseModel):
    status: str
    id: str


class BatchIngestResponse(BaseModel):
    indexed: int
    errors: int


class HealthResponse(BaseModel):
    status: str
    elasticsearch: str
    jina: str
```

**Why separate?** Keeps `main.py` focused on routing/orchestration. Models are importable by tests or other modules.

---

## Phase 2: Bulk Indexing (`vectordb.py`)

**Goal**: Add `bulk_index_documents` to `vectordb.py` using the Elasticsearch `helpers.bulk` API.

**Add to `modal/vectordb.py`**:

```python
from elasticsearch.helpers import bulk


def bulk_index_documents(
    client: Elasticsearch,
    documents: list[dict],
) -> tuple[int, int]:
    """Bulk index observations. Each dict must have content, metadata, embedding.
    Returns (success_count, error_count).
    """
    actions = [
        {
            "_index": ES_INDEX,
            "_source": {
                "content": doc["content"],
                "metadata": doc["metadata"],
                "embedding": doc["embedding"],
            },
        }
        for doc in documents
    ]
    success, errors = bulk(client, actions, raise_on_error=False)
    return success, len(errors) if isinstance(errors, list) else errors
```

**Context7 confirmation**: The `helpers.bulk` pattern from `elasticsearch-py` is the recommended approach for batch ingestion. It handles chunking and retries internally.

---

## Phase 3: Modal App + FastAPI Routes (`main.py`)

**Goal**: Create the Modal app entrypoint with all three API routes.

**Create `modal/main.py`**:

```python
import modal

image = modal.Image.debian_slim().pip_install(
    "fastapi[standard]", "elasticsearch", "requests"
)
app = modal.App("treehacks-vector-search", image=image)


@app.function(
    secrets=[
        modal.Secret.from_name("jina-secret"),
        modal.Secret.from_name("elastic-secret"),
    ],
)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, HTTPException

    from embeddings import get_embeddings
    from models import (
        BatchIngestRequest,
        BatchIngestResponse,
        HealthResponse,
        IngestRequest,
        IngestResponse,
    )
    from vectordb import bulk_index_documents, get_client, ensure_index, index_document

    web_app = FastAPI(title="TreeHacks Vector Search")
    es = get_client()
    ensure_index(es)

    @web_app.post("/ingest", status_code=201, response_model=IngestResponse)
    async def ingest(req: IngestRequest):
        if not req.content.strip():
            raise HTTPException(400, "content must be a non-empty string")
        embedding = get_embeddings([req.content])[0]
        meta = req.metadata.model_dump() if req.metadata else {}
        doc_id = index_document(es, req.content, meta, embedding)
        return IngestResponse(status="indexed", id=doc_id)

    @web_app.post("/ingest/batch", response_model=BatchIngestResponse)
    async def ingest_batch(req: BatchIngestRequest):
        if not req.documents:
            raise HTTPException(400, "documents list must not be empty")
        texts = [doc.content for doc in req.documents]
        embeddings = get_embeddings(texts)
        docs = [
            {
                "content": doc.content,
                "metadata": doc.metadata.model_dump() if doc.metadata else {},
                "embedding": emb,
            }
            for doc, emb in zip(req.documents, embeddings)
        ]
        success, errors = bulk_index_documents(es, docs)
        return BatchIngestResponse(indexed=success, errors=errors)

    @web_app.get("/health", response_model=HealthResponse)
    async def health():
        try:
            es.info()
            es_status = "connected"
        except Exception:
            es_status = "unreachable"
        return HealthResponse(status="ok", elasticsearch=es_status, jina="reachable")

    return web_app
```

**Context7 confirmation**: The `@modal.asgi_app()` decorator pattern is correct — the function returns a FastAPI instance and Modal serves it as an ASGI app with a public HTTPS URL. Secrets are injected via `modal.Secret.from_name()` and exposed as environment variables.

---

## Phase 4: Modal Secrets + Deployment

### 4.1 Create Modal Secrets

```bash
cd modal/
source .env
modal secret create jina-secret JINA_API_KEY=$JINA_API_KEY
modal secret create elastic-secret ES_API_KEY=$ES_API_KEY
```

### 4.2 Deploy

```bash
modal deploy main.py
```

Modal outputs a public URL:
```
https://alemanb--treehacks-vector-search-web.modal.run
```

---

## Phase 5: Validation

### 5.1 Health Check

```bash
curl https://alemanb--treehacks-vector-search-web.modal.run/health
```

Expected:
```json
{"status": "ok", "elasticsearch": "connected", "jina": "reachable"}
```

### 5.2 Single Ingest

```bash
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "content": "A blue hardcover book was moved from the desk to the shelf.",
    "metadata": {
      "object": "book",
      "color": "blue",
      "timestamp": "2026-02-13T14:30:05Z",
      "motion_vector": [0.5, -0.3],
      "device_id": "jetson_super_01"
    }
  }'
```

Expected `201`:
```json
{"status": "indexed", "id": "<es_doc_id>"}
```

### 5.3 Batch Ingest

```bash
curl -X POST https://alemanb--treehacks-vector-search-web.modal.run/ingest/batch \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {"content": "Red mug placed on kitchen counter.", "metadata": {"object": "mug", "color": "red", "device_id": "jetson_01"}},
      {"content": "Black laptop opened on the desk.", "metadata": {"object": "laptop", "color": "black", "device_id": "jetson_01"}}
    ]
  }'
```

Expected `200`:
```json
{"indexed": 2, "errors": 0}
```

### 5.4 Verify in Elasticsearch

```bash
curl -X GET "https://my-elasticsearch-project-dfd764.es.us-central1.gcp.elastic.cloud:443/observations-v1/_count" \
  -H "Authorization: ApiKey $ES_API_KEY"
```

---

## Phase Summary

| Phase | Deliverable | Files Changed |
|-------|-------------|---------------|
| 1 | Pydantic models | `models.py` (new) |
| 2 | Bulk indexing | `vectordb.py` (edit) |
| 3 | Modal + FastAPI app | `main.py` (new) |
| 4 | Secrets + deploy | CLI commands |
| 5 | Validation | curl tests |

## Key Design Decisions

1. **Models in separate file** — keeps `main.py` clean, models reusable for tests
2. **`helpers.bulk`** over manual loop — handles chunking/retries, standard ES pattern (confirmed via Context7)
3. **`@modal.asgi_app()`** over `@modal.fastapi_endpoint()`** — single app with multiple routes under one URL (confirmed via Context7)
4. **Imports inside `web()`** — Modal serializes the function; local imports avoid serialization issues with the ES client
5. **ES client initialized at function scope** — reused across requests within the same container lifecycle
