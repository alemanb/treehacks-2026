"""Matching Function - Orchestrates Elasticsearch search and AI-powered likelihood scoring."""

import json
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
from src.services.temporal_detector import calculate_temporal_filter

from .matching_agent import matching_agent


def search_with_conditions(
    es_client,
    query_vector: List[float],
    conditions: SearchConditions,
    max_results: int = 10,
) -> tuple[List[Dict], int]:
    """
    Execute Elasticsearch search with temporal conditions.

    PHASE 3: Temporal filtering uses hard-coded temporal_detector service.
    - Only applies LOWER bound (earliest_timestamp)
    - No UPPER bound - items can be found anytime after loss event
    - Confidence-based uncertainty buffers applied by temporal_detector

    Args:
        es_client: Elasticsearch client
        query_vector: Query embedding vector
        conditions: Search conditions with temporal filter
        max_results: Maximum number of results to return

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

    # Add temporal filter if needed (LOWER BOUND ONLY)
    if conditions.basedOnEarliestTime and conditions.earliest_timestamp:
        # Apply range filter: timestamp >= earliest_timestamp
        # No upper bound - items can be found anytime after the loss event
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


def format_results_for_agent(
    hits: List[Dict],
    original_query: str,
    expanded_query: str,
    conditions: SearchConditions,
) -> str:
    """
    Format search results into a clear text format for the AI agent to evaluate.

    PHASE 3: Updated to reflect new temporal detection system with confidence-based
    uncertainty buffers (lower bound only, no upper bounds).

    Args:
        hits: Elasticsearch search results
        original_query: User's original query
        expanded_query: Expanded search terms
        conditions: Search conditions applied

    Returns:
        Formatted string for agent input
    """
    prompt = f"""Evaluate these search results for the query: "{original_query}"

**Query Context:**
- Original Query: {original_query}
- Expanded Query: {expanded_query}
- Temporal Filter: {"Yes (lower bound only)" if conditions.basedOnEarliestTime else "No"}
"""

    if conditions.basedOnEarliestTime and conditions.earliest_timestamp:
        prompt += f"- Earliest Timestamp: {conditions.earliest_timestamp}\n"
        prompt += f"- Filter Type: Results from this time onward (no upper bound)\n"
        # Include temporal reasoning if available
        if "Temporal Filter:" in conditions.reasoning:
            # Extract the temporal filter reasoning
            temporal_part = conditions.reasoning.split("Temporal Filter:")[1].strip()
            # Extract confidence level if present
            if "confidence" in temporal_part.lower():
                prompt += f"- Temporal Reasoning: {temporal_part[:200]}\n"  # Truncate if too long

    prompt += "\n**Search Results to Evaluate:**\n\n"

    for idx, hit in enumerate(hits):
        source = hit["_source"]
        metadata = source.get("metadata", {})
        vector_score = hit["_score"]

        prompt += f"Result {idx}:\n"
        prompt += f"  Content: {source['content']}\n"
        prompt += f"  Vector Similarity: {vector_score:.4f}\n"
        prompt += f"  Object: {metadata.get('object', 'N/A')}\n"
        prompt += f"  Color: {metadata.get('color', 'N/A')}\n"
        prompt += f"  Timestamp: {metadata.get('timestamp', 'N/A')}\n"
        prompt += f"  Device: {metadata.get('device_id', 'N/A')}\n"
        prompt += f"  Motion: {metadata.get('motion_vector', 'N/A')}\n"
        prompt += "\n"

    return prompt


def intelligent_matching_function(step_input: StepInput) -> StepOutput:
    """
    Execute intelligent matching with AI-powered likelihood scoring.

    This function:
    1. Gets search results from Elasticsearch
    2. Formats results for AI evaluation
    3. Uses matching_agent (GPT-4o) to intelligently score each result
    4. Returns structured MatchingResponse

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

        # Parse structured outputs with proper type handling
        # Agno returns structured outputs as Pydantic models or dicts
        if isinstance(expansion_content, QueryExpansion):
            expansion = expansion_content
        elif isinstance(expansion_content, str):
            expansion = QueryExpansion.model_validate_json(expansion_content)
        elif isinstance(expansion_content, dict):
            expansion = QueryExpansion(**expansion_content)
        else:
            raise ValueError(f"Unexpected expansion type: {type(expansion_content)}")

        if isinstance(conditions_content, SearchConditions):
            conditions = conditions_content
        elif isinstance(conditions_content, str):
            conditions = SearchConditions.model_validate_json(conditions_content)
        elif isinstance(conditions_content, dict):
            conditions = SearchConditions(**conditions_content)
        else:
            raise ValueError(f"Unexpected conditions type: {type(conditions_content)}")

        # PHASE 3: Calculate temporal filter if temporal indicators detected
        if conditions.basedOnEarliestTime:
            temporal_filter = calculate_temporal_filter(original_query)

            if temporal_filter:
                # Update conditions with calculated temporal boundaries
                conditions.earliest_timestamp = temporal_filter.earliest_timestamp.isoformat()
                # Note: time_window_minutes is deprecated - we only set lower bounds
                conditions.reasoning = (
                    f"{conditions.reasoning}. "
                    f"Temporal Filter: {temporal_filter.reasoning}"
                )

        # Get max_results from additional_data
        max_results = (
            step_input.additional_data.get("max_results", 10)
            if step_input.additional_data
            else 10
        )

        # Embed expanded query with timeout handling
        try:
            query_embedding = get_query_embedding(expansion.expanded_query)
        except Exception as embed_error:
            # If embedding fails, return informative error
            error_msg = str(embed_error)
            if "timed out" in error_msg.lower():
                error_detail = "Jina embedding service timed out. This can happen during high load. Please try again."
            else:
                error_detail = f"Embedding service error: {error_msg}"

            return StepOutput(
                content=json.dumps(
                    {
                        "error": error_detail,
                        "query": str(original_query),
                        "expanded_query": expansion.expanded_query,
                        "results": [],
                        "total_count": 0,
                        "conditions_applied": conditions.model_dump() if hasattr(conditions, 'model_dump') else conditions,
                    }
                ),
                success=False,
            )

        # Search with conditions
        es_client = get_client()
        hits, total_count = search_with_conditions(
            es_client, query_embedding, conditions, max_results
        )

        if not hits:
            # No results found
            return StepOutput(
                content=MatchingResponse(
                    query=str(original_query),
                    expanded_query=expansion.expanded_query,
                    results=[],
                    total_count=0,
                    conditions_applied=conditions,
                ).model_dump_json(),
                success=True,
            )

        # Format results for AI agent evaluation
        agent_prompt = format_results_for_agent(
            hits, str(original_query), expansion.expanded_query, conditions
        )

        # Get AI-powered likelihood scores
        agent_response = matching_agent.run(agent_prompt)

        # Parse agent evaluation
        try:
            evaluation = agent_response.content

            # Handle different response types
            if hasattr(evaluation, 'model_dump'):
                # Pydantic object - convert to dict
                evaluation_dict = evaluation.model_dump()
            elif isinstance(evaluation, str):
                # JSON string - parse it
                evaluation_dict = json.loads(evaluation)
            elif isinstance(evaluation, dict):
                # Already a dict
                evaluation_dict = evaluation
            else:
                raise ValueError(f"Unexpected evaluation type: {type(evaluation)}")

        except Exception as parse_error:
            # Fallback: use vector scores if agent parsing fails
            print(f"Agent parsing error: {parse_error}")
            print(f"Agent response type: {type(agent_response.content)}")
            print(f"Agent response content: {agent_response.content}")
            evaluation_dict = {
                "evaluations": [
                    {
                        "result_index": idx,
                        "likelihood_score": min(100, int(hit["_score"] * 100)),
                        "reasoning": "Fallback: based on vector similarity only",
                    }
                    for idx, hit in enumerate(hits)
                ]
            }

        # Create score lookup
        score_map = {
            eval_item["result_index"]: eval_item
            for eval_item in evaluation_dict.get("evaluations", [])
        }

        # Build final results with AI scores
        results = []
        for idx, hit in enumerate(hits):
            source = hit["_source"]
            vector_score = hit["_score"]

            # Get AI-assigned likelihood score
            eval_item = score_map.get(idx, {})
            likelihood_score = eval_item.get(
                "likelihood_score", min(100, int(vector_score * 100))
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
            query=str(original_query),
            expanded_query=expansion.expanded_query,
            results=results,
            total_count=total_count,
            conditions_applied=conditions,
        )

        return StepOutput(content=response.model_dump_json(), success=True)

    except Exception as e:
        import traceback

        traceback.print_exc()
        return StepOutput(
            content=json.dumps(
                {
                    "error": f"Matching function failed: {str(e)}",
                    "query": step_input.input or "",
                    "results": [],
                    "total_count": 0,
                }
            ),
            success=False,
        )
