"""Unit tests for temporal detection service."""

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from src.services.temporal_detector import (
    detect_temporal_expressions,
    parse_temporal_boundary,
    apply_confidence_adjustment,
    calculate_temporal_filter,
)

# Reference time: Sunday, Feb 15, 2026, 10:00 UTC
REFERENCE_TIME = datetime(2026, 2, 15, 10, 0, 0, tzinfo=ZoneInfo("UTC"))


def test_detect_weekday():
    """Test detection of specific weekday."""
    result = detect_temporal_expressions("lost my glasses on Tuesday")
    assert result is not None
    assert result.raw_text == "tuesday"
    assert result.expression_type == "weekday"
    assert result.confidence >= 0.95


def test_detect_yesterday():
    """Test detection of 'yesterday'."""
    result = detect_temporal_expressions("blue book taken yesterday")
    assert result is not None
    assert result.raw_text == "yesterday"
    assert result.expression_type == "relative_day"
    assert result.confidence >= 0.95


def test_detect_recently():
    """Test detection of vague temporal expression."""
    result = detect_temporal_expressions("red item recently")
    assert result is not None
    assert result.raw_text == "recently"
    assert result.expression_type == "relative_time"
    assert result.confidence < 0.8


def test_no_temporal():
    """Test that non-temporal queries return None."""
    result = detect_temporal_expressions("blue backpack")
    assert result is None


def test_urgency_boost():
    """Test confidence boost from urgency words."""
    result1 = detect_temporal_expressions("blue thing yesterday")
    result2 = detect_temporal_expressions("blue thing stolen yesterday")
    assert result2.confidence > result1.confidence
    assert "stolen" in result2.context_words


def test_parse_tuesday():
    """Test parsing 'Tuesday' relative to Sunday Feb 15."""
    expression = detect_temporal_expressions("item on Tuesday")
    boundary = parse_temporal_boundary(expression, REFERENCE_TIME)

    # Tuesday was Feb 10, 2026 (5 days ago, most recent Tuesday)
    expected = datetime(2026, 2, 10, 0, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert boundary.exact_time == expected


def test_parse_yesterday():
    """Test parsing 'yesterday'."""
    expression = detect_temporal_expressions("item yesterday")
    boundary = parse_temporal_boundary(expression, REFERENCE_TIME)

    # Yesterday was Feb 14, 2026
    expected = datetime(2026, 2, 14, 0, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert boundary.exact_time == expected


def test_high_confidence_strict():
    """Test high confidence creates strict boundary with no buffer."""
    expression = detect_temporal_expressions("stolen on Tuesday")
    boundary = parse_temporal_boundary(expression, REFERENCE_TIME)
    config = apply_confidence_adjustment(boundary, expression.confidence)

    assert config.confidence_level == "strict"
    assert config.uncertainty_buffer_days == 0
    assert config.earliest_timestamp == boundary.exact_time


def test_medium_confidence_flexible():
    """Test medium confidence creates flexible boundary with 1-day buffer."""
    # Create a medium confidence expression manually
    expression = detect_temporal_expressions("item last hour")
    boundary = parse_temporal_boundary(expression, REFERENCE_TIME)
    config = apply_confidence_adjustment(boundary, 0.7)  # Medium confidence

    assert config.confidence_level == "flexible"
    assert config.uncertainty_buffer_days == 1
    # Should search from 1 day before the calculated time
    expected = boundary.exact_time - timedelta(days=1)
    assert config.earliest_timestamp == expected


def test_low_confidence_flexible():
    """Test low confidence creates very flexible boundary with 3-day buffer."""
    expression = detect_temporal_expressions("item a while ago")
    boundary = parse_temporal_boundary(expression, REFERENCE_TIME)
    config = apply_confidence_adjustment(boundary, 0.5)

    assert config.confidence_level == "very_flexible"
    assert config.uncertainty_buffer_days == 3
    # Should search from 3 days before the calculated time
    expected = boundary.exact_time - timedelta(days=3)
    assert config.earliest_timestamp == expected


def test_end_to_end_tuesday():
    """Test full pipeline with 'Tuesday'."""
    config = calculate_temporal_filter(
        "I lost my glasses on Tuesday", current_time=REFERENCE_TIME
    )

    assert config is not None
    assert config.confidence_level == "strict"
    # Tuesday Feb 10, 2026 (most recent Tuesday from Sunday Feb 15)
    expected = datetime(2026, 2, 10, 0, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert config.earliest_timestamp == expected
    assert config.uncertainty_buffer_days == 0


def test_end_to_end_yesterday_stolen():
    """Test full pipeline with 'yesterday' and urgency word."""
    config = calculate_temporal_filter(
        "blue book stolen yesterday", current_time=REFERENCE_TIME
    )

    assert config is not None
    assert config.confidence_level == "strict"  # High confidence due to specific day + urgency
    # Yesterday Feb 14, 2026
    expected = datetime(2026, 2, 14, 0, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert config.earliest_timestamp == expected


def test_end_to_end_recently():
    """Test full pipeline with 'recently'."""
    config = calculate_temporal_filter(
        "red item recently", current_time=REFERENCE_TIME
    )

    assert config is not None
    # Recently has base confidence of 0.60, so should be "flexible" (1-day buffer)
    assert config.confidence_level == "flexible"
    assert config.uncertainty_buffer_days == 1


def test_end_to_end_no_temporal():
    """Test full pipeline with no temporal indicators."""
    config = calculate_temporal_filter("blue backpack", current_time=REFERENCE_TIME)

    assert config is None


def test_time_of_day_last_night():
    """Test detection and parsing of 'last night'."""
    result = detect_temporal_expressions("I saw it last night")
    assert result is not None
    assert result.raw_text == "last night"
    assert result.expression_type == "time_of_day"


def test_time_range_last_week():
    """Test detection of 'last week'."""
    result = detect_temporal_expressions("I lost it last week")
    assert result is not None
    assert result.expression_type == "time_range"
    # Confidence is 0.75 because "lost" is an urgency word (+0.05 boost)
    assert result.confidence == 0.75


def test_multiple_temporal_expressions():
    """Test that first temporal expression is detected when multiple exist."""
    result = detect_temporal_expressions("I lost it yesterday and found it today")
    assert result is not None
    # Should detect the first one (yesterday)
    assert result.raw_text == "yesterday"
