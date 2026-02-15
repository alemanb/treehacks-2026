import modal

image = (
    modal.Image.debian_slim()
    .pip_install("fastapi[standard]", "elasticsearch", "requests")
    .add_local_python_source("config")
    .add_local_python_source("embeddings")
    .add_local_python_source("vectordb")
    .add_local_python_source("models")
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
    from fastapi.middleware.cors import CORSMiddleware

    from embeddings import get_embeddings, get_query_embedding
    from models import (
        BatchIngestRequest,
        BatchIngestResponse,
        HealthResponse,
        IngestRequest,
        IngestResponse,
        Metadata,
        SearchRequest,
        SearchResponse,
        SearchResult,
    )
    from vectordb import (
        bulk_index_documents,
        ensure_index,
        get_client,
        index_document,
        search_similar,
    )

    web_app = FastAPI(title="TreeHacks Vector Search")

    # Add CORS middleware to allow frontend requests
    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:5174",  # Alternative Vite port
            "http://localhost:3000",  # Common React dev server port
        ],
        allow_credentials=True,
        allow_methods=["*"],  # Allow all HTTP methods (GET, POST, etc.)
        allow_headers=["*"],  # Allow all headers
    )

    # Lazy ES init — avoids blocking app startup if ES is slow/unreachable
    _es_client = None
    _index_ready = False

    def _get_es():
        nonlocal _es_client, _index_ready
        if _es_client is None:
            _es_client = get_client()
        if not _index_ready:
            ensure_index(_es_client)
            _index_ready = True
        return _es_client

    @web_app.post("/ingest", status_code=201, response_model=IngestResponse)
    async def ingest(req: IngestRequest):
        if not req.content.strip():
            raise HTTPException(400, "content must be a non-empty string")
        es = _get_es()
        embedding = get_embeddings([req.content])[0]
        meta = req.metadata.model_dump() if req.metadata else {}
        doc_id = index_document(es, req.content, meta, embedding)
        return IngestResponse(status="indexed", id=doc_id)

    @web_app.post("/ingest/batch", response_model=BatchIngestResponse)
    async def ingest_batch(req: BatchIngestRequest):
        if not req.documents:
            raise HTTPException(400, "documents list must not be empty")
        es = _get_es()
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
            es = _get_es()
            es.info()
            es_status = "connected"
        except Exception as e:
            es_status = f"error: {e}"
        return HealthResponse(status="ok", elasticsearch=es_status, jina="reachable")

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

    return web_app
