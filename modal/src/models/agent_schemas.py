"""Pydantic schemas for multi-agent workflow data structures."""

from typing import List, Optional

from pydantic import BaseModel, Field


class QueryExpansion(BaseModel):
    """Output from Query Expansion Agent."""

    original_query: str = Field(description="The original user query")
    expanded_query: str = Field(
        description="Expanded query with synonyms and related terms, comma-separated"
    )
    expansion_terms: List[str] = Field(
        description="Individual expansion terms for reference"
    )
    reasoning: str = Field(description="Brief explanation of expansion strategy")


class SearchConditions(BaseModel):
    """Output from Condition Agent.

    NOTE: As of Phase 2 (Temporal Detection Enhancement):
    - Condition Agent only DETECTS temporal indicators (basedOnEarliestTime flag)
    - Timestamp calculation is handled by temporal_detector service (hard-coded)
    - confidence and time_window_minutes are DEPRECATED
    """

    basedOnEarliestTime: bool = Field(
        description="If true, query contains temporal indicators that will be processed by temporal_detector",
        default=False,
    )
    confidence: bool = Field(
        description="DEPRECATED: No longer used by Condition Agent. Confidence is now calculated by temporal_detector service. Kept for backward compatibility.",
        default=False,
    )
    earliest_timestamp: Optional[str] = Field(
        description=(
            "ISO 8601 timestamp for earliest observation to consider (lower bound only). "
            "This field is populated by temporal_detector service after agent detection. "
            "Represents the calculated start time with confidence-based uncertainty buffer applied. "
            "No upper bound - items can be found anytime after this timestamp."
        ),
        default=None,
    )
    time_window_minutes: Optional[int] = Field(
        description=(
            "DEPRECATED: Removed in favor of uncertainty_buffer_days approach. "
            "The new temporal detection system only adjusts lower bounds (no upper bounds). "
            "Use uncertainty_buffer_days from temporal_detector instead. "
            "Kept for backward compatibility."
        ),
        default=None,
    )
    reasoning: str = Field(
        description=(
            "Explanation of temporal detection. "
            "Initial reasoning from Condition Agent (temporal indicator detection). "
            "Enhanced with temporal_detector reasoning (confidence level, buffer calculation)."
        ),
        default="No temporal conditions detected",
    )


class MatchingResult(BaseModel):
    """Single search result with likelihood score."""

    id: str = Field(description="Elasticsearch document ID")
    content: str = Field(description="Original observation content")
    likelihood_score: int = Field(
        description="Calculated likelihood score 0-100", ge=0, le=100
    )
    vector_score: float = Field(description="Raw cosine similarity score")
    metadata: dict = Field(description="Document metadata")
    timestamp: str = Field(description="Observation timestamp")


class MatchingResponse(BaseModel):
    """Complete response from Matching Agent."""

    query: str = Field(description="Original query")
    expanded_query: str = Field(description="Expanded search terms")
    results: List[MatchingResult] = Field(description="Ranked results")
    total_count: int = Field(description="Total matching documents")
    conditions_applied: SearchConditions = Field(description="Conditions used")


class IntelligentSearchRequest(BaseModel):
    """Request schema for /search/intelligent endpoint."""

    query: str = Field(description="Natural language search query")
    max_results: int = Field(
        description="Maximum number of results to return", default=10, ge=1, le=200
    )
