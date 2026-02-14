# TreeHacks Vector Search

Serverless observation ingestion pipeline that receives events from edge devices (Jetson), embeds them via Jina AI, and stores them in Elasticsearch for vector search.

## Architecture

```
Edge Device (Jetson)
    │  POST /ingest
    ▼
Modal App (FastAPI)
    ├── Jina AI  →  1024-dim embedding
    └── Elasticsearch Cloud  →  document + vector storage
```

## API

**Base URL**: `https://alemanb--treehacks-vector-search-web.modal.run`

### `POST /ingest`

Ingest a single observation. Embeds the `content` field and stores the full document in Elasticsearch.

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

- `content` (required) — natural language description, the only field sent to Jina for embedding
- `metadata` (optional) — structured fields stored as-is for filtering

**Response** `201`:
```json
{
  "status": "indexed",
  "id": "<elasticsearch_doc_id>"
}
```

### `POST /ingest/batch`

Ingest multiple observations in a single request. All `content` strings are embedded in one Jina API call, then bulk-indexed into Elasticsearch.

**Request**:
```json
{
  "documents": [
    { "content": "Red mug placed on kitchen counter.", "metadata": { "object": "mug", "color": "red", "device_id": "jetson_01" } },
    { "content": "Black laptop opened on the desk.", "metadata": { "object": "laptop", "color": "black", "device_id": "jetson_01" } }
  ]
}
```

**Response** `200`:
```json
{
  "indexed": 2,
  "errors": 0
}
```

### `GET /health`

Health check. Returns connectivity status for Elasticsearch and Jina.

**Response** `200`:
```json
{
  "status": "ok",
  "elasticsearch": "connected",
  "jina": "reachable"
}
```

## Metadata Fields

All metadata fields are optional and stored as-is in Elasticsearch for filtering.

| Field | Type | ES Mapping | Purpose |
|-------|------|------------|---------|
| `object` | string | `keyword` | Object class label |
| `color` | string | `keyword` | Color attribute |
| `timestamp` | ISO 8601 | `date` | Event time from device |
| `motion_vector` | float[] | `float` | 2D motion direction |
| `device_id` | string | `keyword` | Source device identifier |

## Project Structure

```
modal/
├── main.py          # Modal app + FastAPI routes
├── models.py        # Pydantic request/response schemas
├── embeddings.py    # Jina AI embeddings client
├── vectordb.py      # Elasticsearch operations
├── config.py        # Constants (endpoints, model, index name)
├── pyproject.toml   # Python dependencies
└── .env             # API keys (gitignored)
```

## Setup

### 1. Install dependencies

```bash
cd modal/
uv sync
```

### 2. Configure secrets

Create `modal/.env`:
```
JINA_API_KEY=<your-jina-key>
ES_API_KEY=<your-elastic-key>
```

Create Modal secrets:
```bash
source .env
modal secret create jina-secret JINA_API_KEY=$JINA_API_KEY
modal secret create elastic-secret ES_API_KEY=$ES_API_KEY
```

### 3. Deploy

```bash
uv run modal deploy main.py
```

### 4. Development (live reload)

```bash
uv run modal serve main.py
```
