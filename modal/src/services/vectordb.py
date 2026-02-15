import os

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from src.config import ES_ENDPOINT, ES_INDEX, JINA_DIMENSIONS


def get_client() -> Elasticsearch:
    return Elasticsearch(ES_ENDPOINT, api_key=os.environ["ES_API_KEY"])


def ensure_index(client: Elasticsearch) -> None:
    if not client.indices.exists(index=ES_INDEX):
        client.indices.create(
            index=ES_INDEX,
            mappings={
                "properties": {
                    "content": {"type": "text"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": JINA_DIMENSIONS,
                        "index": True,
                        "similarity": "cosine",
                    },
                    "metadata": {
                        "properties": {
                            "object": {"type": "keyword"},
                            "color": {"type": "keyword"},
                            "timestamp": {"type": "date"},
                            "motion_vector": {"type": "float"},
                            "device_id": {"type": "keyword"},
                        }
                    },
                }
            },
        )


def index_document(
    client: Elasticsearch, content: str, metadata: dict, embedding: list[float]
) -> str:
    """Index a single observation. Returns the document ID."""
    result = client.index(
        index=ES_INDEX,
        document={
            "content": content,
            "metadata": metadata,
            "embedding": embedding,
        },
    )
    return result["_id"]


def bulk_index_documents(
    client: Elasticsearch, documents: list[dict]
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
    error_count = len(errors) if isinstance(errors, list) else errors
    return success, error_count


def search_similar(
    client: Elasticsearch,
    query_vector: list[float],
    page: int = 1,
    page_size: int = 10,
    max_page_size: int = 100,
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
        - results: List of dicts with _id, _score, _source (content and metadata)
        - total_count: Total number of matching documents in the index

    Raises:
        ValueError: If page < 1 or page_size not in [1, max_page_size]

    Example:
        >>> hits, total = search_similar(es_client, query_emb, page=2, page_size=10)
        >>> print(f"Showing results 11-20 of {total}")

    Context7 Reference:
        /elastic/elasticsearch-py — kNN search with pagination via from_ and size
    """
    # Input validation
    if page < 1:
        raise ValueError("page must be >= 1")
    if not (1 <= page_size <= max_page_size):
        raise ValueError(f"page_size must be between 1 and {max_page_size}")

    # Calculate offset (0-indexed for Elasticsearch)
    offset = (page - 1) * page_size

    # Dynamic num_candidates scaling for deep pagination
    # Rule: num_candidates should be at least 10x (offset + page_size) for accuracy
    # Minimum of 1000 to ensure quality results for early pages
    num_candidates = max(1000, 10 * (offset + page_size))

    # For pagination to work properly with kNN, we need to fetch enough candidates
    # Set k to a reasonable maximum (e.g., 200) so we can paginate through results
    # This ensures we get enough total results for multiple pages
    k_value = min(num_candidates, 200)  # Limit to 200 to balance performance

    # Perform kNN search with pagination parameters
    response = client.search(
        index=ES_INDEX,
        knn={
            "field": "embedding",
            "query_vector": query_vector,
            "k": k_value,                    # Fetch more results for pagination
            "num_candidates": num_candidates,  # Candidates to consider
        },
        from_=offset,                    # Skip offset results (0-indexed)
        size=page_size,                  # Return page_size results
        track_total_hits=True,           # Get accurate total count (not capped at 10k)
        _source=["content", "metadata"],  # Exclude embedding from response
    )

    # Extract results and total count
    hits = response["hits"]["hits"]

    # Get total count (handle both exact and estimated counts)
    total_info = response["hits"]["total"]
    if isinstance(total_info, dict):
        total_count = total_info["value"]
        # Note: total_info["relation"] can be "eq" (exact) or "gte" (estimated)
    else:
        total_count = total_info  # Older ES versions return int directly

    return hits, total_count
