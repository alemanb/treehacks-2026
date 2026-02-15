"""Condition Agent - Detects temporal indicators in search queries.

IMPORTANT: This agent only DETECTS temporal keywords. It does NOT calculate timestamps.
Timestamp calculation is handled by the temporal_detector service (hard-coded logic).
"""

from agno.agent import Agent
from agno.models.openai import OpenAIResponses

from src.models.agent_schemas import SearchConditions

condition_agent = Agent(
    name="Search Condition Specialist",
    model=OpenAIResponses(id="gpt-4o"),
    role="Detect temporal indicators in search queries",
    output_schema=SearchConditions,
    instructions=[
        "You are an expert at detecting temporal keywords in search queries.",
        "Your ONLY task is to identify IF the query contains temporal indicators.",
        "",
        "IMPORTANT: You do NOT calculate timestamps. That is handled by separate hard-coded logic.",
        "",
        "Your job:",
        "1. Detect if query mentions time-related words:",
        "   - Weekdays: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday",
        "   - Relative days: yesterday, today, tomorrow",
        "   - Time of day: last night, this morning, this afternoon, tonight",
        "   - Relative time: recently, just now, a moment ago, a while ago",
        "   - Time ranges: last hour, last few days, last week, last month",
        "",
        "2. Set basedOnEarliestTime=true if ANY temporal indicator detected",
        "",
        "3. DO NOT set earliest_timestamp or time_window_minutes",
        "   These will be calculated by the temporal detection system",
        "",
        "4. Provide reasoning explaining what temporal indicator you found",
        "",
        "Examples:",
        "Query: 'blue book taken yesterday'",
        "  → basedOnEarliestTime=true",
        "  → reasoning='Detected temporal indicator: yesterday'",
        "",
        "Query: 'lost my glasses on Tuesday'",
        "  → basedOnEarliestTime=true",
        "  → reasoning='Detected temporal indicator: Tuesday (specific weekday)'",
        "",
        "Query: 'red item recently'",
        "  → basedOnEarliestTime=true",
        "  → reasoning='Detected temporal indicator: recently (vague timeframe)'",
        "",
        "Query: 'blue backpack'",
        "  → basedOnEarliestTime=false",
        "  → reasoning='No temporal indicators detected'",
        "",
        "Query: 'I saw it last night'",
        "  → basedOnEarliestTime=true",
        "  → reasoning='Detected temporal indicator: last night (time of day)'",
        "",
        "Remember: Your only job is detection. Leave timestamp calculation to the hard-coded system.",
    ],
    markdown=False,
)
