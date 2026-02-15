"""FastAPI application with all API routes for vector search."""

import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.models import (
    BatchIngestRequest,
    BatchIngestResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    IntelligentSearchRequest,
    MatchingResponse,
    Metadata,
    PaginationMetadata,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from src.services import (
    bulk_index_documents,
    ensure_index,
    get_client,
    get_embeddings,
    get_query_embedding,
    index_document,
    search_similar,
)
from src.workflows import intelligent_rag_workflow


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
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

    @web_app.post("/search/intelligent", response_model=MatchingResponse)
    async def intelligent_search(req: IntelligentSearchRequest):
        """
        Intelligent vector search using multi-agent workflow.

        This endpoint uses a multi-agent system to:
        1. Expand the query with related terms (Query Expansion Agent)
        2. Determine temporal and confidence conditions (Condition Agent)
        3. Execute smart search with likelihood scoring (Matching Agent)

        The workflow provides better results for ambiguous queries and
        automatically handles temporal filtering.

        Request:
            {
                "query": "blue thing taken yesterday",
                "max_results": 10
            }

        Response:
            {
                "query": "...",
                "expanded_query": "...",
                "results": [{...}],
                "total_count": 15,
                "conditions_applied": {...}
            }
        """
        # Validate query
        if not req.query.strip():
            raise HTTPException(400, "query must be a non-empty string")

        try:
            # Run the multi-agent workflow
            workflow_response = intelligent_rag_workflow.run(
                input=req.query, additional_data={"max_results": req.max_results}
            )

            # Parse the final output from matching agent
            try:
                matching_response = MatchingResponse.model_validate_json(
                    workflow_response.content
                )
            except Exception as parse_error:
                # If parsing fails, try to extract error information for better debugging
                try:
                    partial_data = json.loads(workflow_response.content) if isinstance(workflow_response.content, str) else workflow_response.content
                    if isinstance(partial_data, dict) and "error" in partial_data:
                        error_msg = partial_data.get("error", "Unknown error")
                        raise HTTPException(
                            500, f"Multi-agent workflow error: {error_msg}"
                        )
                except json.JSONDecodeError:
                    pass  # Not JSON, continue with original error

                # If we get here, it's a parsing/validation error
                raise HTTPException(
                    500, f"Failed to parse workflow response: {str(parse_error)}"
                )

            return matching_response

        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            # Log the error for debugging
            import traceback

            traceback.print_exc()
            raise HTTPException(
                500, f"Intelligent search workflow failed: {str(e)}"
            )

    return web_app
