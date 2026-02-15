#!/usr/bin/env python3
"""Test each agent individually to identify which one is failing."""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.agents import query_expansion_agent, condition_agent


def test_query_expansion():
    """Test the Query Expansion Agent."""
    print("\n" + "=" * 60)
    print("Testing Query Expansion Agent")
    print("=" * 60)

    test_query = "blue thing"
    print(f"Input: {test_query}")

    try:
        response = query_expansion_agent.run(test_query)
        print(f"\n✅ SUCCESS!")
        print(f"Response type: {type(response)}")
        print(f"Content: {response.content}")

        # Try to parse the content
        import json
        if isinstance(response.content, str):
            parsed = json.loads(response.content)
            print(f"\nParsed response:")
            print(f"  - Original Query: {parsed.get('original_query')}")
            print(f"  - Expanded Query: {parsed.get('expanded_query')}")
            print(f"  - Expansion Terms: {parsed.get('expansion_terms')}")
            print(f"  - Reasoning: {parsed.get('reasoning')}")

        return True, response

    except Exception as e:
        print(f"\n❌ FAILED!")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, None


def test_condition_agent():
    """Test the Condition Agent."""
    print("\n" + "=" * 60)
    print("Testing Condition Agent")
    print("=" * 60)

    test_queries = [
        "blue thing",  # No temporal
        "blue book taken yesterday",  # Temporal strict
        "red item recently",  # Temporal loose
    ]

    all_passed = True

    for query in test_queries:
        print(f"\nInput: {query}")

        try:
            response = condition_agent.run(query)
            print(f"✅ SUCCESS!")
            print(f"Response type: {type(response)}")
            print(f"Content: {response.content}")

            # Try to parse the content
            import json
            if isinstance(response.content, str):
                parsed = json.loads(response.content)
                print(f"\nParsed response:")
                print(f"  - Based on Time: {parsed.get('basedOnEarliestTime')}")
                print(f"  - Confidence: {parsed.get('confidence')}")
                print(f"  - Earliest Timestamp: {parsed.get('earliest_timestamp')}")
                print(f"  - Time Window: {parsed.get('time_window_minutes')}")
                print(f"  - Reasoning: {parsed.get('reasoning')}")

        except Exception as e:
            print(f"❌ FAILED!")
            print(f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
            all_passed = False

    return all_passed


def main():
    """Run all tests."""
    print("\n" + "🔍 AGENT DIAGNOSTICS" + "\n")

    # Test 1: Query Expansion Agent
    expansion_passed, expansion_response = test_query_expansion()

    # Test 2: Condition Agent
    condition_passed = test_condition_agent()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Query Expansion Agent: {'✅ PASS' if expansion_passed else '❌ FAIL'}")
    print(f"Condition Agent:       {'✅ PASS' if condition_passed else '❌ FAIL'}")

    if expansion_passed and condition_passed:
        print("\n✅ All agents working correctly!")
        print("\nNext steps:")
        print("1. Run: modal deploy main.py")
        print("2. Test: curl -X POST <url>/search/intelligent ...")
    else:
        print("\n❌ Some agents are failing!")
        print("\nPossible causes:")
        print("1. OpenAI API key not set (check OPENAI_API_KEY)")
        print("2. Model 'gpt-4o' not available (check OpenAI account)")
        print("3. Network connectivity issues")

    return 0 if (expansion_passed and condition_passed) else 1


if __name__ == "__main__":
    sys.exit(main())
