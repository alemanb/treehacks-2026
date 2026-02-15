"""Temporal detection and parsing service.

This module provides hard-coded temporal expression detection and parsing
for natural language date expressions like "Tuesday", "yesterday", and "recently".

It implements confidence-based temporal filtering with:
- High confidence (≥0.9): Strict boundaries (exact date onward, 0-day buffer)
- Medium confidence (0.6-0.9): Flexible boundaries (1-day earlier, uncertainty buffer)
- Low confidence (<0.6): Very flexible boundaries (3-days earlier, larger uncertainty buffer)

IMPORTANT: Only adjusts lower bounds - no upper bounds (items can be found anytime after loss).
"""

import re
from datetime import datetime, timedelta
from typing import Optional, List
from dataclasses import dataclass
import dateparser
from zoneinfo import ZoneInfo


@dataclass
class TemporalExpression:
    """Detected temporal expression from query."""

    raw_text: str  # e.g., "Tuesday", "yesterday"
    expression_type: str  # "weekday", "relative_day", "time_of_day", "relative_time"
    confidence: float  # 0.0-1.0
    context_words: List[str]  # ["stolen", "taken"] for urgency detection


@dataclass
class TemporalBoundary:
    """Calculated time boundary."""

    exact_time: datetime  # Precise timestamp
    description: str  # Human-readable description


@dataclass
class FilterConfig:
    """Final filter configuration for Elasticsearch."""

    earliest_timestamp: datetime
    uncertainty_buffer_days: int  # How many days earlier we search (0, 1, or 3)
    confidence_level: str  # "strict", "flexible", "very_flexible"
    reasoning: str  # Explanation for debugging


# Temporal keyword patterns
TEMPORAL_PATTERNS = {
    "weekday": {
        "pattern": r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        "base_confidence": 0.95,
    },
    "relative_day": {
        "pattern": r"\b(yesterday|today|tomorrow)\b",
        "base_confidence": 0.95,
    },
    "time_of_day": {
        "pattern": r"\b(last night|this morning|this afternoon|this evening|tonight)\b",
        "base_confidence": 0.90,
    },
    "relative_time": {
        "pattern": r"\b(recently|just now|a moment ago|a while ago)\b",
        "base_confidence": 0.60,
    },
    "time_range": {
        "pattern": r"\b(last (hour|few hours|day|few days|week|month)|an? (hour|day|week|month) ago)\b",
        "base_confidence": 0.70,
    },
}

# Urgency indicators that increase confidence
URGENCY_WORDS = ["stolen", "taken", "missing", "lost", "disappeared", "gone"]


def detect_temporal_expressions(query: str) -> Optional[TemporalExpression]:
    """
    Detect temporal expressions in the query and calculate confidence.

    Args:
        query: User's search query

    Returns:
        TemporalExpression if detected, None otherwise
    """
    query_lower = query.lower()

    # Check each pattern type
    for expr_type, config in TEMPORAL_PATTERNS.items():
        match = re.search(config["pattern"], query_lower)
        if match:
            raw_text = match.group(0)
            confidence = config["base_confidence"]

            # Check for urgency words to boost confidence
            context_words = [word for word in URGENCY_WORDS if word in query_lower]
            if context_words:
                confidence = min(1.0, confidence + 0.05)  # Boost by 5%

            return TemporalExpression(
                raw_text=raw_text,
                expression_type=expr_type,
                confidence=confidence,
                context_words=context_words,
            )

    return None


def parse_temporal_boundary(
    expression: TemporalExpression,
    current_time: Optional[datetime] = None,
) -> TemporalBoundary:
    """
    Calculate exact timestamp from temporal expression.

    Args:
        expression: Detected temporal expression
        current_time: Reference time (defaults to UTC now)

    Returns:
        TemporalBoundary with exact timestamp
    """
    if current_time is None:
        current_time = datetime.now(ZoneInfo("UTC"))

    # Use dateparser with settings
    settings = {
        "RELATIVE_BASE": current_time,
        "TIMEZONE": "UTC",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "past",  # Assume past events
    }

    # Parse the expression
    parsed_time = dateparser.parse(expression.raw_text, settings=settings)

    if parsed_time is None:
        # Fallback: use current time if parsing fails
        parsed_time = current_time

    # For weekdays in the past, find the most recent occurrence
    if expression.expression_type == "weekday":
        # dateparser might return future date, ensure it's in the past
        if parsed_time > current_time:
            parsed_time = parsed_time - timedelta(days=7)

    # Set time to start of relevant period
    if expression.expression_type in ["weekday", "relative_day"]:
        # Set to start of day (00:00:00)
        parsed_time = parsed_time.replace(hour=0, minute=0, second=0, microsecond=0)

    description = f"Parsed '{expression.raw_text}' as {parsed_time.isoformat()}"

    return TemporalBoundary(
        exact_time=parsed_time,
        description=description,
    )


def apply_confidence_adjustment(
    boundary: TemporalBoundary,
    confidence: float,
) -> FilterConfig:
    """
    Apply confidence-based adjustments to temporal boundary.

    IMPORTANT: Only adjusts the LOWER bound (how far back to search).
    No upper bound - items can be found anytime after the loss event.

    High confidence (≥0.9): Search from exact date onward
    Medium confidence (0.6-0.9): Search from 1 day before onward (uncertainty buffer)
    Low confidence (<0.6): Search from 3 days before onward (larger uncertainty buffer)

    Args:
        boundary: Calculated temporal boundary
        confidence: Confidence level (0.0-1.0)

    Returns:
        FilterConfig with adjusted lower bound only
    """
    if confidence >= 0.9:
        # Strict boundary - exact date only
        earliest_timestamp = boundary.exact_time
        uncertainty_buffer_days = 0
        confidence_level = "strict"
        reasoning = (
            f"High confidence ({confidence:.2f}): strict boundary starting at "
            f"{earliest_timestamp.isoformat()}. Results from this exact time onward."
        )

    elif 0.6 <= confidence < 0.9:
        # Flexible boundary - 1 day earlier for uncertainty
        earliest_timestamp = boundary.exact_time - timedelta(days=1)
        uncertainty_buffer_days = 1
        confidence_level = "flexible"
        reasoning = (
            f"Medium confidence ({confidence:.2f}): flexible boundary with 1-day "
            f"uncertainty buffer. Results from {earliest_timestamp.isoformat()} onward "
            f"(1 day before calculated time to account for uncertainty)."
        )

    else:  # confidence < 0.6
        # Very flexible boundary - 3 days earlier for uncertainty
        earliest_timestamp = boundary.exact_time - timedelta(days=3)
        uncertainty_buffer_days = 3
        confidence_level = "very_flexible"
        reasoning = (
            f"Low confidence ({confidence:.2f}): very flexible boundary with 3-day "
            f"uncertainty buffer. Results from {earliest_timestamp.isoformat()} onward "
            f"(3 days before calculated time to account for high uncertainty)."
        )

    return FilterConfig(
        earliest_timestamp=earliest_timestamp,
        uncertainty_buffer_days=uncertainty_buffer_days,
        confidence_level=confidence_level,
        reasoning=reasoning,
    )


def calculate_temporal_filter(
    query: str,
    current_time: Optional[datetime] = None,
) -> Optional[FilterConfig]:
    """
    Main function: detect temporal expression and calculate filter config.

    Args:
        query: User's search query
        current_time: Reference time (defaults to UTC now)

    Returns:
        FilterConfig if temporal expression detected, None otherwise
    """
    # Step 1: Detect temporal expressions
    expression = detect_temporal_expressions(query)
    if expression is None:
        return None

    # Step 2: Parse to exact timestamp
    boundary = parse_temporal_boundary(expression, current_time)

    # Step 3: Apply confidence adjustment
    filter_config = apply_confidence_adjustment(boundary, expression.confidence)

    return filter_config
