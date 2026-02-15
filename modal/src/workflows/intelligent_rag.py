"""Intelligent RAG Workflow - Multi-agent query expansion and conditional matching."""

from agno.workflow import Step, Workflow

from src.agents import (
    condition_agent,
    intelligent_matching_function,
    query_expansion_agent,
)

intelligent_rag_workflow = Workflow(
    name="Intelligent RAG Workflow",
    description="Multi-agent query expansion and conditional matching for enhanced search",
    steps=[
        Step(
            name="expand_query",
            agent=query_expansion_agent,
            description="Expand user query with related terms and synonyms",
        ),
        Step(
            name="determine_conditions",
            agent=condition_agent,
            description="Analyze query for temporal and confidence requirements",
        ),
        Step(
            name="match_results",
            executor=intelligent_matching_function,
            description="Search Elasticsearch and use AI to intelligently score result likelihood",
        ),
    ],
)
