"""Integration tests for Phase 3 - Matching Function with Temporal Detection."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import Mock, patch

from src.models.agent_schemas import SearchConditions, QueryExpansion
from src.services.temporal_detector import calculate_temporal_filter


# Reference time for testing: Sunday, Feb 15, 2026, 10:00 UTC
REFERENCE_TIME = datetime(2026, 2, 15, 10, 0, 0, tzinfo=ZoneInfo("UTC"))


def test_temporal_filter_integration_tuesday():
    """Test end-to-end temporal filter for 'Tuesday' query."""
    query = "I lost my glasses on Tuesday"

    # Simulate Condition Agent output (Phase 2)
    conditions = SearchConditions(
        basedOnEarliestTime=True,
        reasoning="Detected temporal indicator: Tuesday (specific weekday)",
    )

    # Calculate temporal filter (Phase 3)
    temporal_filter = calculate_temporal_filter(query, REFERENCE_TIME)

    assert temporal_filter is not None
    assert temporal_filter.confidence_level == "strict"
    assert temporal_filter.uncertainty_buffer_days == 0

    # Verify timestamp is correct (Tuesday Feb 10, 2026)
    expected_timestamp = datetime(2026, 2, 10, 0, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert temporal_filter.earliest_timestamp == expected_timestamp

    # Update conditions as matching_function would
    conditions.earliest_timestamp = temporal_filter.earliest_timestamp.isoformat()
    conditions.reasoning = (
        f"{conditions.reasoning}. Temporal Filter: {temporal_filter.reasoning}"
    )

    # Verify final conditions
    assert conditions.earliest_timestamp == "2026-02-10T00:00:00+00:00"
    assert "strict boundary" in conditions.reasoning
    assert "Temporal Filter:" in conditions.reasoning


def test_temporal_filter_integration_yesterday():
    """Test end-to-end temporal filter for 'yesterday' query."""
    query = "blue book stolen yesterday"

    # Simulate Condition Agent output
    conditions = SearchConditions(
        basedOnEarliestTime=True,
        reasoning="Detected temporal indicator: yesterday",
    )

    # Calculate temporal filter
    temporal_filter = calculate_temporal_filter(query, REFERENCE_TIME)

    assert temporal_filter is not None
    assert temporal_filter.confidence_level == "strict"  # High confidence + urgency word

    # Verify timestamp (yesterday = Feb 14, 2026)
    expected_timestamp = datetime(2026, 2, 14, 0, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert temporal_filter.earliest_timestamp == expected_timestamp

    # Update conditions
    conditions.earliest_timestamp = temporal_filter.earliest_timestamp.isoformat()
    conditions.reasoning = f"{conditions.reasoning}. Temporal Filter: {temporal_filter.reasoning}"

    assert conditions.earliest_timestamp == "2026-02-14T00:00:00+00:00"


def test_temporal_filter_integration_recently():
    """Test end-to-end temporal filter for 'recently' query."""
    query = "red item recently"

    # Simulate Condition Agent output
    conditions = SearchConditions(
        basedOnEarliestTime=True,
        reasoning="Detected temporal indicator: recently (vague timeframe)",
    )

    # Calculate temporal filter
    temporal_filter = calculate_temporal_filter(query, REFERENCE_TIME)

    assert temporal_filter is not None
    assert temporal_filter.confidence_level == "flexible"  # Medium confidence
    assert temporal_filter.uncertainty_buffer_days == 1

    # Verify 1-day buffer is applied
    # "recently" parsed as ~2 hours ago, minus 1 day buffer
    assert temporal_filter.earliest_timestamp < REFERENCE_TIME

    # Update conditions
    conditions.earliest_timestamp = temporal_filter.earliest_timestamp.isoformat()
    conditions.reasoning = f"{conditions.reasoning}. Temporal Filter: {temporal_filter.reasoning}"

    assert "flexible boundary" in conditions.reasoning
    assert "1-day" in conditions.reasoning


def test_temporal_filter_integration_no_temporal():
    """Test that queries without temporal indicators skip temporal filtering."""
    query = "blue backpack"

    # Simulate Condition Agent output
    conditions = SearchConditions(
        basedOnEarliestTime=False,
        reasoning="No temporal indicators detected",
    )

    # Calculate temporal filter (should return None)
    temporal_filter = calculate_temporal_filter(query, REFERENCE_TIME)

    assert temporal_filter is None

    # Conditions should remain unchanged
    assert conditions.earliest_timestamp is None
    assert conditions.basedOnEarliestTime is False


def test_elasticsearch_query_construction():
    """Test that Elasticsearch query is correctly constructed with temporal filter."""
    from src.agents.matching_function import search_with_conditions

    # Mock Elasticsearch client
    mock_es = Mock()
    mock_es.search.return_value = {
        "hits": {
            "hits": [],
            "total": {"value": 0}
        }
    }

    # Create conditions with temporal filter
    conditions = SearchConditions(
        basedOnEarliestTime=True,
        earliest_timestamp="2026-02-10T00:00:00+00:00",
        reasoning="Test temporal filter",
    )

    query_vector = [0.1] * 768  # Mock embedding

    # Execute search
    hits, total = search_with_conditions(mock_es, query_vector, conditions, max_results=10)

    # Verify Elasticsearch was called
    assert mock_es.search.called

    # Get the search body that was passed
    call_args = mock_es.search.call_args
    search_body = call_args[1]["body"]

    # Verify temporal filter is in the query
    assert "query" in search_body
    assert "bool" in search_body["query"]
    assert "filter" in search_body["query"]["bool"]

    # Verify range filter
    range_filter = search_body["query"]["bool"]["filter"][0]
    assert "range" in range_filter
    assert "metadata.timestamp" in range_filter["range"]
    assert "gte" in range_filter["range"]["metadata.timestamp"]
    assert range_filter["range"]["metadata.timestamp"]["gte"] == "2026-02-10T00:00:00+00:00"

    # Verify NO upper bound (no "lte" key)
    assert "lte" not in range_filter["range"]["metadata.timestamp"]


def test_elasticsearch_query_no_temporal():
    """Test that Elasticsearch query works without temporal filter."""
    from src.agents.matching_function import search_with_conditions

    # Mock Elasticsearch client
    mock_es = Mock()
    mock_es.search.return_value = {
        "hits": {
            "hits": [],
            "total": {"value": 0}
        }
    }

    # Create conditions WITHOUT temporal filter
    conditions = SearchConditions(
        basedOnEarliestTime=False,
        reasoning="No temporal conditions",
    )

    query_vector = [0.1] * 768

    # Execute search
    hits, total = search_with_conditions(mock_es, query_vector, conditions, max_results=10)

    # Verify Elasticsearch was called
    assert mock_es.search.called

    # Get the search body
    call_args = mock_es.search.call_args
    search_body = call_args[1]["body"]

    # Verify NO temporal filter in the query
    assert "query" not in search_body or search_body.get("query") is None


def test_confidence_levels():
    """Test that different queries get appropriate confidence levels."""
    test_cases = [
        # (query, expected_confidence_level, expected_buffer_days)
        ("lost glasses on Tuesday", "strict", 0),
        ("stolen wallet yesterday", "strict", 0),
        ("saw it last night", "strict", 0),
        ("red item recently", "flexible", 1),
        ("lost it last week", "flexible", 1),
        # Note: "a while ago" has base confidence 0.60, which is exactly at the
        # threshold between medium (0.6-0.9) and low (<0.6), so it's "flexible"
        ("saw it a while ago", "flexible", 1),
    ]

    for query, expected_level, expected_buffer in test_cases:
        temporal_filter = calculate_temporal_filter(query, REFERENCE_TIME)

        assert temporal_filter is not None, f"Failed for query: {query}"
        assert temporal_filter.confidence_level == expected_level, \
            f"Wrong confidence for '{query}': expected {expected_level}, got {temporal_filter.confidence_level}"
        assert temporal_filter.uncertainty_buffer_days == expected_buffer, \
            f"Wrong buffer for '{query}': expected {expected_buffer}, got {temporal_filter.uncertainty_buffer_days}"


def test_lower_bound_only():
    """Verify that temporal filters only set lower bounds, never upper bounds."""
    queries = [
        "lost my glasses on Tuesday",
        "stolen yesterday",
        "saw it recently",
        "last week",
    ]

    for query in queries:
        temporal_filter = calculate_temporal_filter(query, REFERENCE_TIME)

        if temporal_filter:
            # Verify we have an earliest_timestamp (lower bound)
            assert temporal_filter.earliest_timestamp is not None

            # Verify reasoning mentions "onward" (no upper bound)
            assert "onward" in temporal_filter.reasoning.lower()

            # Verify no mention of "until", "before", or upper bounds
            assert "until" not in temporal_filter.reasoning.lower()
            assert "before" not in temporal_filter.reasoning.lower() or "before calculated" in temporal_filter.reasoning.lower()
