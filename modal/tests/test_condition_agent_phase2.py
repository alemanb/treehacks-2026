"""Test updated Condition Agent (Phase 2) - Temporal indicator detection only."""

import pytest
from src.agents.condition import condition_agent


def test_condition_agent_detects_yesterday():
    """Test that agent detects 'yesterday' temporal indicator."""
    result = condition_agent.run("blue book taken yesterday")

    assert result.basedOnEarliestTime is True
    assert "yesterday" in result.reasoning.lower()
    # Agent should NOT set these - handled by temporal_detector
    assert result.earliest_timestamp is None
    assert result.time_window_minutes is None


def test_condition_agent_detects_tuesday():
    """Test that agent detects specific weekday."""
    result = condition_agent.run("I lost my glasses on Tuesday")

    assert result.basedOnEarliestTime is True
    assert "tuesday" in result.reasoning.lower()
    # Agent should NOT set timestamps
    assert result.earliest_timestamp is None


def test_condition_agent_detects_recently():
    """Test that agent detects vague temporal expression."""
    result = condition_agent.run("red item recently")

    assert result.basedOnEarliestTime is True
    assert "recently" in result.reasoning.lower()
    # Agent should NOT set timestamps
    assert result.earliest_timestamp is None


def test_condition_agent_no_temporal():
    """Test that agent correctly identifies no temporal indicators."""
    result = condition_agent.run("blue backpack")

    assert result.basedOnEarliestTime is False
    assert "no temporal" in result.reasoning.lower()
    assert result.earliest_timestamp is None
    assert result.time_window_minutes is None


def test_condition_agent_last_night():
    """Test detection of time of day expression."""
    result = condition_agent.run("I saw it last night")

    assert result.basedOnEarliestTime is True
    assert "last night" in result.reasoning.lower()


def test_condition_agent_last_week():
    """Test detection of time range expression."""
    result = condition_agent.run("lost it last week")

    assert result.basedOnEarliestTime is True
    assert "last week" in result.reasoning.lower()


def test_condition_agent_complex_query():
    """Test detection with complex query."""
    result = condition_agent.run("I'm looking for a blue book with red cover that I lost yesterday morning")

    assert result.basedOnEarliestTime is True
    # Should detect either "yesterday" or "morning" or both
    reasoning_lower = result.reasoning.lower()
    assert "yesterday" in reasoning_lower or "morning" in reasoning_lower


def test_condition_agent_no_timestamp_calculation():
    """Verify agent does NOT calculate timestamps (delegated to temporal_detector)."""
    result = condition_agent.run("lost my wallet on Monday")

    assert result.basedOnEarliestTime is True
    # Critical: Agent should NOT populate these fields
    assert result.earliest_timestamp is None
    assert result.time_window_minutes is None
    # Only reasoning should be populated
    assert result.reasoning != "No temporal conditions detected"
