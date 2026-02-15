"""Pydantic models for API requests and responses."""

from .agent_schemas import (
    IntelligentSearchRequest,
    MatchingResponse,
    MatchingResult,
    QueryExpansion,
    SearchConditions,
)
from .schemas import (
    BatchIngestRequest,
    BatchIngestResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    Metadata,
    PaginationMetadata,
    SearchRequest,
    SearchResponse,
    SearchResult,
)

__all__ = [
    # Existing schemas
    "BatchIngestRequest",
    "BatchIngestResponse",
    "HealthResponse",
    "IngestRequest",
    "IngestResponse",
    "Metadata",
    "PaginationMetadata",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    # New agent schemas
    "IntelligentSearchRequest",
    "MatchingResponse",
    "MatchingResult",
    "QueryExpansion",
    "SearchConditions",
]
