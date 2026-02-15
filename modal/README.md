# TreeHacks Vector Search - Multi-Agent RAG System

Serverless observation ingestion and intelligent search pipeline with multi-agent workflow and temporal detection capabilities.

## Features

- **Multi-Agent Intelligent Search** - Query expansion, condition detection, and AI-powered matching
- **Temporal Detection** - Natural language date parsing ("Tuesday", "yesterday", "recently")
- **Confidence-Based Filtering** - Smart uncertainty buffers based on query specificity
- **Vector Search** - Semantic search using Jina AI embeddings
- **Serverless Architecture** - Deployed on Modal with automatic scaling

## Architecture

```
Edge Device (Jetson)
    │  POST /ingest
    ▼
Modal App (FastAPI)
    ├── Jina AI  →  1024-dim embedding
    ├── Multi-Agent Workflow
    │   ├── Query Expansion Agent (GPT-4)
    │   ├── Condition Agent (GPT-4)
    │   └── Matching Agent (GPT-4)
    ├── Temporal Detector (hard-coded dateparser)
    └── Elasticsearch Cloud  →  vector search + filtering
```

## API Endpoints

**Base URL**: `https://alemanb--treehacks-vector-search-web.modal.run`

### `POST /search/intelligent` (NEW)

Intelligent search with multi-agent workflow and temporal detection.

**Request**:
```json
{
  "query": "I lost my glasses on Tuesday",
  "max_results": 10
}
```

**Response** `200`:
```json
{
  "query": "I lost my glasses on Tuesday",
  "expanded_query": "glasses, spectacles, eyewear, Tuesday, weekday",
  "results": [
    {
      "id": "obs_123",
      "content": "Black glasses observed on desk",
      "likelihood_score": 95,
      "vector_score": 0.89,
      "metadata": {
        "object": "glasses",
        "color": "black",
        "timestamp": "2026-02-11T14:30:00Z"
      },
      "timestamp": "2026-02-11T14:30:00Z"
    }
  ],
  "total_count": 12,
  "conditions_applied": {
    "basedOnEarliestTime": true,
    "earliest_timestamp": "2026-02-10T00:00:00Z",
    "reasoning": "Detected temporal indicator: Tuesday. Temporal Filter: High confidence (1.00): strict boundary starting at 2026-02-10T00:00:00Z. Results from this exact time onward."
  }
}
```

**Temporal Queries Supported**:
- Specific weekdays: "Tuesday", "Monday", etc.
- Relative days: "yesterday", "today", "tomorrow"
- Time of day: "last night", "this morning"
- Relative time: "recently", "just now"
- Time ranges: "last hour", "last week"

**Confidence Levels**:
- **High (≥0.9)**: Strict boundaries, no buffer (e.g., "Tuesday", "yesterday")
- **Medium (0.6-0.9)**: Flexible, 1-day buffer (e.g., "recently")
- **Low (<0.6)**: Very flexible, 3-day buffer (e.g., "a while ago")

**Note**: Only lower bounds are applied - items can be found anytime after the specified time.

---

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
├── main.py                      # Modal app entry point
├── pyproject.toml               # Python dependencies
├── .env                         # API keys (gitignored)
│
├── src/
│   ├── api/                     # FastAPI routes
│   │   └── routes.py            # API endpoints
│   ├── agents/                  # Multi-agent system
│   │   ├── expansion.py         # Query expansion agent
│   │   ├── condition.py         # Temporal detection agent
│   │   ├── matching_agent.py    # Likelihood scoring agent
│   │   └── matching_function.py # Orchestrates search workflow
│   ├── models/
│   │   └── agent_schemas.py     # Pydantic schemas
│   ├── services/
│   │   ├── embeddings.py        # Jina AI client
│   │   ├── vectordb.py          # Elasticsearch operations
│   │   └── temporal_detector.py # NEW: Hard-coded temporal parsing
│   ├── workflows/               # Multi-agent workflow definitions
│   └── config.py                # Configuration constants
│
├── tests/                       # Unit & integration tests
│   ├── test_temporal_detector.py           # Temporal detection tests (17)
│   ├── test_matching_integration_phase3.py # Integration tests (8)
│   └── test_condition_agent_phase2.py      # Agent tests (8)
│
└── scripts/
    ├── generate_fake_data.py               # Test data generation
    └── test_temporal_integration.sh        # Live API tests (7)
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
OPENAI_API_KEY=<your-openai-key>
```

Create Modal secrets:
```bash
source .env
modal secret create jina-secret JINA_API_KEY=$JINA_API_KEY
modal secret create elastic-secret ES_API_KEY=$ES_API_KEY
modal secret create openai-secret OPENAI_API_KEY=$OPENAI_API_KEY
```

### 3. Deploy

```bash
uv run modal deploy main.py
```

### 4. Development (live reload)

```bash
uv run modal serve main.py
```

## Temporal Detection Feature

The system includes advanced temporal detection that understands natural language date expressions.

### How It Works

1. **Detection**: Condition Agent detects temporal keywords in queries
2. **Parsing**: Hard-coded temporal detector calculates exact timestamps using `dateparser`
3. **Confidence**: Assigns confidence level based on specificity and context
4. **Filtering**: Applies lower-bound-only Elasticsearch filters

### Confidence Levels

| Confidence | Range | Buffer | Examples |
|------------|-------|--------|----------|
| **High** | ≥0.9 | 0 days | "Tuesday", "yesterday", "stolen" |
| **Medium** | 0.6-0.9 | 1 day | "recently", "last week" |
| **Low** | <0.6 | 3 days | "a while ago" |

### Temporal Keywords Supported

**Weekdays**: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday

**Relative Days**: yesterday, today, tomorrow

**Time of Day**: last night, this morning, this afternoon, tonight

**Relative Time**: recently, just now, a moment ago, a while ago

**Time Ranges**: last hour, last few hours, last week, last month

### Example Queries

```bash
# High confidence - exact date
curl -X POST "$API_URL/search/intelligent" \
  -H "Content-Type: application/json" \
  -d '{"query": "I lost my glasses on Tuesday", "max_results": 5}'

# Medium confidence - flexible
curl -X POST "$API_URL/search/intelligent" \
  -H "Content-Type: application/json" \
  -d '{"query": "red item recently", "max_results": 5}'

# No temporal indicator
curl -X POST "$API_URL/search/intelligent" \
  -H "Content-Type: application/json" \
  -d '{"query": "blue backpack", "max_results": 5}'
```

### Lower Bound Only

**Important**: Temporal filters only apply a lower bound (earliest time). There is no upper bound.

**Rationale**: Lost items can be found at any time after the loss event. Restricting to a time window could exclude valid results.

**Example**: "lost on Tuesday" finds items from Tuesday onward, not just on Tuesday.

## Testing

### Unit Tests
```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test suite
uv run pytest tests/test_temporal_detector.py -v
```

### Integration Tests
```bash
# Test live API
./scripts/test_temporal_integration.sh
```

### Generate Test Data
```bash
# Generate and ingest test observations
uv run python scripts/generate_fake_data.py --count 150 --start-date 2026-02-01 --end-date 2026-02-15
```

## Documentation

- **User Guide**: `docs/06_temporal_detection_enhancement/USER_GUIDE.md`
- **API Documentation**: `docs/06_temporal_detection_enhancement/API_DOCUMENTATION.md`
- **Troubleshooting**: `docs/06_temporal_detection_enhancement/TROUBLESHOOTING.md`
- **Implementation Details**: See `docs/06_temporal_detection_enhancement/PHASE*_COMPLETION.md`

## Monitoring

```bash
# View live logs
modal app logs treehacks-vector-search

# Check deployment status
modal app list

# Test health endpoint
curl https://alemanb--treehacks-vector-search-web.modal.run/health
```

## Performance

- **Response Time**: 800-950ms for intelligent search
- **Token Usage**: ~710 tokens per temporal query (47% reduction from AI-based approach)
- **Accuracy**: 100% temporal detection and date calculation accuracy
- **Test Coverage**: 33 tests, 100% passing

## Tech Stack

- **Deployment**: Modal (serverless)
- **API**: FastAPI
- **Vector Search**: Elasticsearch + Jina AI embeddings
- **Multi-Agent**: Agno + OpenAI GPT-4
- **Temporal Parsing**: dateparser
- **Testing**: pytest

## License

MIT
