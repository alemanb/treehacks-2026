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

    from embeddings import get_embeddings
    from models import (
        BatchIngestRequest,
        BatchIngestResponse,
        HealthResponse,
        IngestRequest,
        IngestResponse,
    )
    from vectordb import bulk_index_documents, ensure_index, get_client, index_document

    web_app = FastAPI(title="TreeHacks Vector Search")

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

    return web_app
