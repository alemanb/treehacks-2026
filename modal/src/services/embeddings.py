import os
import time
from typing import List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import JINA_API_URL, JINA_MODEL

# Configuration for timeouts and retries
JINA_TIMEOUT = 90  # Increased from 30s to 90s for multi-agent workflows
JINA_CONNECT_TIMEOUT = 10  # Connection timeout
JINA_READ_TIMEOUT = 80  # Read timeout (within total timeout)
MAX_RETRIES = 3
RETRY_BACKOFF = 0.5  # Exponential backoff factor


def _create_session_with_retries() -> requests.Session:
    """Create a requests session with retry logic and connection pooling.

    Retry strategy:
    - Retry on network errors (ConnectionError, Timeout)
    - Retry on specific HTTP status codes (500, 502, 503, 504)
    - Exponential backoff between retries
    - Connection pooling for performance
    """
    session = requests.Session()

    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=20,
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


# Global session for connection pooling
_jina_session = _create_session_with_retries()


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts via Jina API with retry logic.

    Features:
    - 90-second timeout (increased from 30s)
    - Automatic retries on network errors
    - Connection pooling for performance
    - Exponential backoff between retries

    Returns:
        List of 1024-dim embedding vectors

    Raises:
        requests.HTTPError: If all retry attempts fail
        requests.Timeout: If request exceeds timeout
    """
    for attempt in range(MAX_RETRIES):
        try:
            response = _jina_session.post(
                JINA_API_URL,
                headers={
                    "Authorization": f"Bearer {os.environ['JINA_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json={"model": JINA_MODEL, "input": texts, "task": "retrieval.passage"},
                timeout=(JINA_CONNECT_TIMEOUT, JINA_READ_TIMEOUT),
            )
            response.raise_for_status()
            return [item["embedding"] for item in response.json()["data"]]

        except requests.Timeout as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_BACKOFF * (2 ** attempt)
                print(f"Jina timeout (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise requests.Timeout(
                    f"Jina API timed out after {MAX_RETRIES} attempts: {str(e)}"
                ) from e

        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_BACKOFF * (2 ** attempt)
                print(f"Jina request failed (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise


def get_query_embedding(query: str) -> list[float]:
    """Embed a search query via Jina API with retry logic.

    Uses 'retrieval.query' task (optimized for short search queries)
    vs. 'retrieval.passage' task (used for document ingestion).

    Features:
    - 90-second timeout (increased from 30s)
    - Automatic retries on network errors
    - Connection pooling for performance
    - Exponential backoff between retries

    Args:
        query: User search query (natural language string)

    Returns:
        1024-dim embedding vector

    Raises:
        requests.HTTPError: If all retry attempts fail
        requests.Timeout: If request exceeds timeout
    """
    for attempt in range(MAX_RETRIES):
        try:
            response = _jina_session.post(
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
                timeout=(JINA_CONNECT_TIMEOUT, JINA_READ_TIMEOUT),
            )
            response.raise_for_status()
            return response.json()["data"][0]["embedding"]

        except requests.Timeout as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_BACKOFF * (2 ** attempt)
                print(f"Jina timeout (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise requests.Timeout(
                    f"Jina API timed out after {MAX_RETRIES} attempts: {str(e)}"
                ) from e

        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_BACKOFF * (2 ** attempt)
                print(f"Jina request failed (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise
