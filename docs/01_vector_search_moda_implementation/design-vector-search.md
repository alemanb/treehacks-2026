# Design: Elastic Vector Database + Jina Embeddings Integration

## Status: IMPLEMENTED
## Date: 2026-02-13

---

## 1. Overview

Integrate Elasticsearch Serverless as the vector database and Jina AI embeddings as the embedding model into the treehacks-2026 project. The system receives observation events from edge devices (Jetson) via a FastAPI HTTP endpoint hosted on Modal, embeds the `content` field using Jina, and stores the full document with its vector in Elasticsearch.

### Goals

- Expose a FastAPI HTTP endpoint on Modal to receive device observation JSON
- Extract `content` from incoming payloads and embed it via Jina AI
- Store full documents (content + metadata + embedding) in Elasticsearch Cloud
- Keep the architecture simple, serverless, and cost-efficient

---

## 2. Architecture

```
┌──────────────────┐   POST /ingest    ┌──────────────────────────────┐
│  Edge Device     │──────────────────▶│  Modal App (FastAPI)         │
│  (Jetson Super)  │                   │                              │
└──────────────────┘                   │  1. Validate JSON            │
                                       │  2. Extract "content"        │
                                       │  3. Embed via Jina API       │
                                       │  4. Store in Elasticsearch   │
                                       └──────────┬───────────────────┘
                                                  │
                              ┌────────────────────┼────────────────────┐
                              ▼                                        ▼
                ┌─────────────────────────┐          ┌─────────────────────────┐
                │  Jina Embeddings API    │          │  Elasticsearch Cloud    │
                │  api.jina.ai/v1/embed   │          │  (Serverless)           │
                │  model: jina-embed-v3   │          │  dense_vector storage   │
                └─────────────────────────┘          └─────────────────────────┘
```

### Component Responsibilities

| Component | Role |
|-----------|------|
| **Edge Device (Jetson)** | Sends observation events as JSON via HTTP POST |
| **Modal App + FastAPI** | HTTP API layer — validates, orchestrates embedding + storage |
| **Jina Embeddings API** | Converts `content` text → 1024-dim dense vector |
| **Elasticsearch Cloud** | Stores documents + vectors for later retrieval |

---

## 3. Input Schema

The system receives JSON payloads from edge devices. **Only the `content` field is embedded**; `metadata` is stored as-is.

### Ingest Payload

```json
{
  "content": "A blue hardcover book was moved from the desk to the shelf.",
  "metadata": {
    "object": "book",
    "color": "blue",
    "timestamp": "2026-02-13T14:30:05Z",
    "motion_vector": [0.5, -0.3],
    "device_id": "jetson_super_01"
  }
}
```

### Field Contract

| Field | Type | Embedded? | Stored in ES? | Purpose |
|-------|------|-----------|---------------|---------|
| `content` | `string` | Yes | Yes (`text`) | Natural language description — the only field sent to Jina |
| `metadata.object` | `string` | No | Yes (`keyword`) | Object class label for filtering |
| `metadata.color` | `string` | No | Yes (`keyword`) | Color attribute for filtering |
| `metadata.timestamp` | `ISO 8601` | No | Yes (`date`) | Event timestamp from device |
| `metadata.motion_vector` | `[float, float]` | No | Yes (`float[]`) | 2D motion direction |
| `metadata.device_id` | `string` | No | Yes (`keyword`) | Source device identifier |

---

## 4. External Dependencies

### 4.1 Elasticsearch (Python Client)

- **Package**: `elasticsearch` (PyPI) — official Python client
- **Version**: `>=8.17`
- **License**: Apache 2.0

**Connection**:
```python
from elasticsearch import Elasticsearch

client = Elasticsearch(
    "https://my-elasticsearch-project-dfd764.es.us-central1.gcp.elastic.cloud:443",
    api_key="<ES_API_KEY>"
)
```

**Key capabilities used**:
- `client.indices.create()` — create index with dense_vector mapping
- `client.index()` — index single document with embedding
- `client.bulk()` — batch document ingestion

### 4.2 Jina AI Embeddings

- **API endpoint**: `https://api.jina.ai/v1/embeddings`
- **Auth**: Bearer token via `JINA_API_KEY` environment variable
- **No SDK required** — plain HTTP `requests` calls
- **License**: Commercial API (pay-per-use)

**Model**: `jina-embeddings-v3`
- Dimensions: **1024**
- Model size: 570M parameters
- Task: `retrieval.passage` (for ingestion embedding)
- Supports: dimension truncation, late chunking, normalization

**API call pattern**:
```python
import requests

response = requests.post(
    "https://api.jina.ai/v1/embeddings",
    headers={
        "Authorization": f"Bearer {JINA_API_KEY}",
        "Content-Type": "application/json",
    },
    json={
        "model": "jina-embeddings-v3",
        "input": ["A blue hardcover book was moved from the desk to the shelf."],
        "task": "retrieval.passage"
    }
)
embedding = response.json()["data"][0]["embedding"]  # list of 1024 floats
```

### 4.3 Modal + FastAPI

- **Modal**: `modal` (already installed, v1.3.3) — serverless compute
- **FastAPI**: Served via `@modal.asgi_app()` decorator — gives a public HTTPS URL
- **Secrets**: `modal.Secret.from_name()` for API keys injected as env vars

**Modal FastAPI pattern**:
```python
import modal

image = modal.Image.debian_slim().pip_install(
    "fastapi[standard]", "elasticsearch", "requests"
)
app = modal.App("treehacks-vector-search", image=image)

@app.function(
    secrets=[modal.Secret.from_name("jina-secret"), modal.Secret.from_name("elastic-secret")]
)
@modal.asgi_app()
def web():
    from fastapi import FastAPI
    web_app = FastAPI()
    # ... define routes ...
    return web_app
```

### 4.4 Python Dependencies (to add to pyproject.toml)

| Package | Purpose |
|---------|---------|
| `elasticsearch>=8.17` | Elasticsearch Python client |
| `requests>=2.31` | HTTP calls to Jina API |
| `fastapi[standard]` | HTTP API framework (served by Modal) |

---

## 5. Elasticsearch Index Design

### 5.1 Index Mapping

```json
{
  "mappings": {
    "properties": {
      "content": {
        "type": "text"
      },
      "embedding": {
        "type": "dense_vector",
        "dims": 1024,
        "index": true,
        "similarity": "cosine"
      },
      "metadata": {
        "properties": {
          "object": { "type": "keyword" },
          "color": { "type": "keyword" },
          "timestamp": { "type": "date" },
          "motion_vector": { "type": "float" },
          "device_id": { "type": "keyword" }
        }
      }
    }
  },
  "settings": {
    "number_of_replicas": 0
  }
}
```

**Design decisions**:
- `content` as `text` — original observation text
- `embedding` as `dense_vector` with 1024 dims — matches Jina v3 output
- `metadata.object`, `metadata.color`, `metadata.device_id` as `keyword` — structured log fields
- `metadata.timestamp` as `date` — event time from device
- `metadata.motion_vector` as `float` array — 2D motion data

### 5.2 Index Name

```
observations-v1
```

---

## 6. API Design (FastAPI Routes)

### `POST /ingest` — Ingest a single observation

**Request**:
```json
{
  "content": "A blue hardcover book was moved from the desk to the shelf.",
  "metadata": {
    "object": "book",
    "color": "blue",
    "timestamp": "2026-02-13T14:30:05Z",
    "motion_vector": [0.5, -0.3],
    "device_id": "jetson_super_01"
  }
}
```

**Processing**:
1. Validate payload (content is required, non-empty string)
2. Call Jina API: embed `content` with `task="retrieval.passage"`
3. Index into Elasticsearch: `content` + `metadata` + `embedding`
4. Return confirmation

**Response** `201`:
```json
{
  "status": "indexed",
  "id": "<elasticsearch_doc_id>"
}
```

### `POST /ingest/batch` — Ingest multiple observations

**Request**:
```json
{
  "documents": [
    { "content": "...", "metadata": { ... } },
    { "content": "...", "metadata": { ... } }
  ]
}
```

**Processing**:
1. Validate all documents
2. Batch embed all `content` strings in a single Jina API call
3. Bulk index into Elasticsearch
4. Return summary

**Response** `200`:
```json
{
  "indexed": 10,
  "errors": 0
}
```

### `GET /health` — Health check

**Response** `200`:
```json
{
  "status": "ok",
  "elasticsearch": "connected",
  "jina": "reachable"
}
```

---

## 7. Module Design

### 7.1 File Structure

```
modal/
├── main.py              # Modal app + FastAPI routes (single entrypoint)
├── embeddings.py        # Jina embeddings client
├── vectordb.py          # Elasticsearch client wrapper
├── config.py            # Constants (endpoint, index name, model)
└── pyproject.toml       # Dependencies
```

### 7.2 `config.py`

```python
ES_ENDPOINT = "https://my-elasticsearch-project-dfd764.es.us-central1.gcp.elastic.cloud:443"
ES_INDEX = "observations-v1"

JINA_API_URL = "https://api.jina.ai/v1/embeddings"
JINA_MODEL = "jina-embeddings-v3"
JINA_DIMENSIONS = 1024
```

### 7.3 `embeddings.py`

```python
import os
import requests
from config import JINA_API_URL, JINA_MODEL

def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts via Jina API. Returns list of 1024-dim vectors."""
    response = requests.post(
        JINA_API_URL,
        headers={
            "Authorization": f"Bearer {os.environ['JINA_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={"model": JINA_MODEL, "input": texts, "task": "retrieval.passage"},
        timeout=30,
    )
    response.raise_for_status()
    return [item["embedding"] for item in response.json()["data"]]
```

### 7.4 `vectordb.py`

```python
import os
from elasticsearch import Elasticsearch
from config import ES_ENDPOINT, ES_INDEX, JINA_DIMENSIONS

def get_client() -> Elasticsearch:
    return Elasticsearch(ES_ENDPOINT, api_key=os.environ["ES_API_KEY"])

def ensure_index(client: Elasticsearch) -> None:
    if not client.indices.exists(index=ES_INDEX):
        client.indices.create(index=ES_INDEX, mappings={...}, settings={...})  # mapping from Section 5

def index_document(client: Elasticsearch, content: str, metadata: dict, embedding: list[float]) -> str:
    """Index a single observation. Returns the document ID."""
    result = client.index(index=ES_INDEX, document={
        "content": content,
        "metadata": metadata,
        "embedding": embedding,
    })
    return result["_id"]
```

### 7.5 `main.py` — Modal App + FastAPI

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
    ]
)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

    from embeddings import get_embeddings
    from vectordb import get_client, ensure_index, index_document

    web_app = FastAPI(title="TreeHacks Vector Search")
    es = get_client()
    ensure_index(es)

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

    @web_app.post("/ingest", status_code=201)
    async def ingest(req: IngestRequest):
        if not req.content.strip():
            raise HTTPException(400, "content must be a non-empty string")
        embedding = get_embeddings([req.content])[0]
        doc_id = index_document(es, req.content, req.metadata.model_dump() if req.metadata else {}, embedding)
        return {"status": "indexed", "id": doc_id}

    @web_app.post("/ingest/batch")
    async def ingest_batch(req: BatchIngestRequest):
        texts = [doc.content for doc in req.documents]
        embeddings = get_embeddings(texts)
        indexed = 0
        errors = 0
        for doc, emb in zip(req.documents, embeddings):
            try:
                index_document(es, doc.content, doc.metadata.model_dump() if doc.metadata else {}, emb)
                indexed += 1
            except Exception:
                errors += 1
        return {"indexed": indexed, "errors": errors}

    @web_app.get("/health")
    async def health():
        return {"status": "ok"}

    return web_app
```

---

## 8. Data Flow

### 8.1 Ingest Flow (per request)

```
Jetson device sends POST /ingest
    │
    ▼
FastAPI validates JSON (Pydantic)
    │
    ▼
Extract doc["content"] only
    │
    ▼
content → Jina API (task="retrieval.passage") → 1024-dim vector
    │
    ▼
Elasticsearch index: { content, metadata (as-is), embedding }
    │
    ▼
Return { status: "indexed", id: "<es_doc_id>" }
```

---

## 9. Secrets Management

API keys are stored locally in a `.env` file and loaded into Modal's secret manager at deploy time. **Never hardcode API keys or commit `.env` to version control.**

### Local `.env` File

Store keys in `modal/.env`:

```env
JINA_API_KEY=<your-jina-key>
ES_API_KEY=<your-elastic-key>
```

Ensure `.env` is gitignored:

```gitignore
# in project root .gitignore
.env
```

### Modal Secrets

Create Modal secrets from the `.env` values:

```bash
source modal/.env
modal secret create jina-secret JINA_API_KEY=$JINA_API_KEY
modal secret create elastic-secret ES_API_KEY=$ES_API_KEY
```

| Secret Name | Env Var | `.env` Key | Source |
|-------------|---------|------------|--------|
| `jina-secret` | `JINA_API_KEY` | `JINA_API_KEY` | https://jina.ai dashboard |
| `elastic-secret` | `ES_API_KEY` | `ES_API_KEY` | Elastic Cloud console |

---

## 10. Error Handling

| Failure | Handling |
|---------|----------|
| Missing/empty `content` | 400 Bad Request |
| Jina API rate limit (429) | Exponential backoff, max 3 retries |
| Jina API timeout | 30s timeout, retry once |
| ES connection failure | Retry with backoff, 503 to caller |
| ES indexing failure | Return error details, 500 to caller |
| Invalid metadata fields | Pydantic validation, 422 to caller |

---

## 11. Implementation Plan

### Phase 1: Foundation
1. Add `elasticsearch`, `requests`, `fastapi[standard]` to `pyproject.toml`
2. Create `config.py` with constants
3. Create `embeddings.py` — Jina client
4. Create `vectordb.py` — Elasticsearch client with index management

### Phase 2: API Layer
5. Rewrite `main.py` — Modal app with FastAPI routes
6. Implement `POST /ingest`, `POST /ingest/batch`, `GET /health`
7. Create Modal secrets for Jina and Elastic API keys

### Phase 3: Validation
8. Deploy to Modal (`modal deploy main.py`)
9. Create index on Elasticsearch Cloud via first `/ingest` call
10. Test ingest with sample Jetson payload
11. Verify documents and embeddings stored correctly in Elasticsearch

### Phase 4: Enhancements (future)
- Async Jina calls with `aiohttp` for lower latency
- Batch ingestion via Modal `.map()` for high-throughput scenarios
- Rate limiting on ingest endpoint
- Authentication (API key or JWT) on endpoints

---

## 12. Deployment

```bash
# From the modal/ directory
modal deploy main.py
```

Modal will output a public HTTPS URL like:
```
https://alemanb--treehacks-vector-search-web.modal.run
```

The Jetson device can then POST to:
- `https://alemanb--treehacks-vector-search-web.modal.run/ingest`
