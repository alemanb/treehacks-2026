"""Business logic services for embeddings and vector database operations."""

from .embeddings import get_embeddings, get_query_embedding
from .vectordb import (
    bulk_index_documents,
    ensure_index,
    get_client,
    index_document,
    search_similar,
)

__all__ = [
    "get_embeddings",
    "get_query_embedding",
    "bulk_index_documents",
    "ensure_index",
    "get_client",
    "index_document",
    "search_similar",
]
