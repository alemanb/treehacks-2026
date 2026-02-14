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
