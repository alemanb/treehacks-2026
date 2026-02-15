import os

import requests

from src.config import JINA_API_URL, JINA_MODEL


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


def get_query_embedding(query: str) -> list[float]:
    """Embed a search query via Jina API using retrieval.query task.

    Uses 'retrieval.query' task (optimized for short search queries)
    vs. 'retrieval.passage' task (used for document ingestion).

    Args:
        query: User search query (natural language string)

    Returns:
        1024-dim embedding vector

    Raises:
        requests.HTTPError: If Jina API request fails
    """
    response = requests.post(
        JINA_API_URL,
        headers={
            "Authorization": f"Bearer {os.environ['JINA_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "model": JINA_MODEL,
            "input": [query],  # Single query in a list
            "task": "retrieval.query",  # Different from ingestion's "retrieval.passage"
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]
