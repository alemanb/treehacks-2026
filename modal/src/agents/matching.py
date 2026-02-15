"""Matching Agent - Executes intelligent search with likelihood scoring."""

import json
from datetime import datetime
from typing import Any, Dict, List

from agno.workflow.types import StepInput, StepOutput

from src.models.agent_schemas import (
    MatchingResponse,
    MatchingResult,
    QueryExpansion,
    SearchConditions,
)
from src.services.embeddings import get_query_embedding
from src.services.vectordb import get_client


def calculate_likelihood_score(
    vector_score: float,
    metadata: Dict[str, Any],
    timestamp: str,
    conditions: SearchConditions,
) -> int:
    """
    Calculate likelihood score (0-100) based on multiple factors.

    Formula:
    - Base score: vector similarity * 70 (0-70 points)
    - Temporal bonus: +10 if within strict time boundary
    - Metadata match bonus: +5 per matching field (up to +20)
    """
    # Base score from vector similarity (0-70 points)
    base_score = vector_score * 70

    # Temporal bonus (0-10 points)
    temporal_bonus = 0
    if conditions.basedOnEarliestTime and conditions.earliest_timestamp:
        try:
            doc_time = datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            )
            earliest_time = datetime.fromisoformat(
                conditions.earliest_timestamp.replace("Z", "+00:00")
            )
            if doc_time >= earliest_time:
                temporal_bonus = 10 if conditions.confidence else 5
        except Exception:
            pass  # Ignore timestamp parsing errors

    # Metadata match bonus (0-20 points)
    # Check if metadata has expected fields with values
    metadata_bonus = 0
    if metadata.get("object"):
        metadata_bonus += 5
    if metadata.get("color"):
        metadata_bonus += 5
    if metadata.get("device_id"):
        metadata_bonus += 5
    if metadata.get("motion_vector"):
        metadata_bonus += 5

    # Calculate total score (capped at 100)
    total_score = base_score + temporal_bonus + metadata_bonus
    return min(100, int(total_score))


def search_with_conditions(
    es_client,
    query_vector: List[float],
    conditions: SearchConditions,
    max_results: int = 10,
) -> tuple[List[Dict], int]:
    """
    Execute Elasticsearch search with temporal conditions.

    Returns:
        Tuple of (results, total_count)
    """
    from src.config import ES_INDEX

    # Build kNN query
    knn_query = {
        "field": "embedding",
        "query_vector": query_vector,
        "k": min(max_results * 10, 200),  # Fetch more candidates for filtering
        "num_candidates": max(1000, max_results * 50),
    }

    # Build search query
    search_body: Dict[str, Any] = {
        "knn": knn_query,
        "size": max_results,
        "_source": ["content", "metadata"],
    }

    # Add temporal filter if needed
    if conditions.basedOnEarliestTime and conditions.earliest_timestamp:
        search_body["query"] = {
            "bool": {
                "filter": [
                    {
                        "range": {
                            "metadata.timestamp": {"gte": conditions.earliest_timestamp}
                        }
                    }
                ]
            }
        }

    # Execute search
    response = es_client.search(index=ES_INDEX, body=search_body)

    hits = response["hits"]["hits"]
    total_info = response["hits"]["total"]
    total_count = (
        total_info["value"] if isinstance(total_info, dict) else total_info
    )

    return hits, total_count


def matching_agent_function(step_input: StepInput) -> StepOutput:
    """
    Execute intelligent matching with likelihood scoring.

    Accesses previous step outputs:
    - expand_query: QueryExpansion
    - determine_conditions: SearchConditions

    Additional data:
    - max_results: int (default: 10)
    """
    try:
        # Get original query
        original_query = step_input.input or ""

        # Get previous step outputs
        expansion_content = step_input.get_step_content("expand_query")
        conditions_content = step_input.get_step_content("determine_conditions")

        if not expansion_content or not conditions_content:
            return StepOutput(
                content=json.dumps(
                    {
                        "error": "Missing previous step outputs",
                        "query": original_query,
                        "results": [],
                        "total_count": 0,
                    }
                ),
                success=False,
            )

        # Parse structured outputs (handle both JSON string and object)
        if isinstance(expansion_content, str):
            expansion = QueryExpansion.model_validate_json(expansion_content)
        else:
            # Already a Pydantic object
            expansion = expansion_content if isinstance(expansion_content, QueryExpansion) else QueryExpansion(**expansion_content)

        if isinstance(conditions_content, str):
            conditions = SearchConditions.model_validate_json(conditions_content)
        else:
            # Already a Pydantic object
            conditions = conditions_content if isinstance(conditions_content, SearchConditions) else SearchConditions(**conditions_content)

        # Get max_results from additional_data
        max_results = step_input.additional_data.get("max_results", 10) if step_input.additional_data else 10

        # Embed expanded query
        query_embedding = get_query_embedding(expansion.expanded_query)

        # Search with conditions
        es_client = get_client()
        hits, total_count = search_with_conditions(
            es_client, query_embedding, conditions, max_results
        )

        # Calculate likelihood scores and format results
        results = []
        for hit in hits:
            source = hit["_source"]
            vector_score = hit["_score"]

            likelihood_score = calculate_likelihood_score(
                vector_score=vector_score,
                metadata=source.get("metadata", {}),
                timestamp=source.get("metadata", {}).get("timestamp", ""),
                conditions=conditions,
            )

            result = MatchingResult(
                id=hit["_id"],
                content=source["content"],
                likelihood_score=likelihood_score,
                vector_score=vector_score,
                metadata=source.get("metadata", {}),
                timestamp=source.get("metadata", {}).get("timestamp", ""),
            )
            results.append(result)

        # Create response
        response = MatchingResponse(
            query=original_query,
            expanded_query=expansion.expanded_query,
            results=results,
            total_count=total_count,
            conditions_applied=conditions,
        )

        return StepOutput(content=response.model_dump_json(), success=True)

    except Exception as e:
        return StepOutput(
            content=json.dumps(
                {
                    "error": f"Matching agent failed: {str(e)}",
                    "query": step_input.input or "",
                    "results": [],
                    "total_count": 0,
                }
            ),
            success=False,
        )
