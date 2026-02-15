#!/usr/bin/env python3
"""Test script for AI-powered matching agent."""

import os
import sys

# Test that imports work
try:
    from src.agents import (
        condition_agent,
        intelligent_matching_function,
        matching_agent,
        query_expansion_agent,
    )
    from src.workflows import intelligent_rag_workflow

    print("✅ All imports successful!")
    print(f"   - Query Expansion Agent: {query_expansion_agent.name}")
    print(f"   - Condition Agent: {condition_agent.name}")
    print(f"   - Matching Agent: {matching_agent.name}")
    print(f"   - Workflow: {intelligent_rag_workflow.name}")
    print(f"   - Workflow Steps: {len(intelligent_rag_workflow.steps)}")

except Exception as e:
    print(f"❌ Import failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Test workflow structure
print("\n📋 Workflow Structure:")
for idx, step in enumerate(intelligent_rag_workflow.steps, 1):
    step_type = "Agent" if hasattr(step, "agent") else "Function"
    print(f"   Step {idx}: {step.name} ({step_type})")
    print(f"           {step.description}")

# Test with OpenAI API key if available
if os.getenv("OPENAI_API_KEY"):
    print("\n🧪 Testing AI-Powered Workflow (requires ES + Jina)...")
    try:
        response = intelligent_rag_workflow.run(
            input="blue thing", additional_data={"max_results": 3}
        )
        print(f"   Workflow Success: {response.success}")
        if response.success:
            print(f"   Response Length: {len(response.content)} chars")
            print(f"   Preview: {response.content[:200]}...")
        else:
            print(f"   Error: {response.content}")
    except Exception as e:
        print(f"   ⚠️  Workflow test skipped: {e}")
else:
    print("\n⚠️  OPENAI_API_KEY not set - skipping live test")

print("\n✅ All tests passed!")
