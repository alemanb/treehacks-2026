import os

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from config import ES_ENDPOINT, ES_INDEX, JINA_DIMENSIONS


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
