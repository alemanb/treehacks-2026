#!/usr/bin/env python3
"""
Comprehensive test suite for intelligent search endpoint.
Usage: python test_intelligent_search.py [base_url]
"""

import json
import sys
from typing import Dict, Any

import requests


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


class IntelligentSearchTester:
    """Test suite for intelligent search endpoint."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.passed = 0
        self.failed = 0
        self.warnings = 0
    
    def print_header(self, title: str):
        """Print a test header."""
        print(f"\n{Colors.BLUE}{'=' * 60}{Colors.NC}")
        print(f"{Colors.BLUE}{title}{Colors.NC}")
        print(f"{Colors.BLUE}{'=' * 60}{Colors.NC}\n")
    
    def print_test(self, name: str, passed: bool, message: str = "", warning: bool = False):
        """Print test result."""
        if warning:
            icon = f"{Colors.YELLOW}⚠️  WARN{Colors.NC}"
            self.warnings += 1
        elif passed:
            icon = f"{Colors.GREEN}✅ PASS{Colors.NC}"
            self.passed += 1
        else:
            icon = f"{Colors.RED}❌ FAIL{Colors.NC}"
            self.failed += 1
        
        print(f"{icon} {name}")
        if message:
            print(f"  {message}")
    
    def test_health(self):
        """Test health endpoint."""
        print("\n📋 Test 1: Health Check")
        print("-" * 40)
        
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            data = response.json()
            
            if response.status_code == 200 and data.get('status') == 'ok':
                self.print_test("Health endpoint", True, f"Status: {data.get('status')}")
                self.print_test("Elasticsearch", data.get('elasticsearch') == 'connected', 
                               f"ES Status: {data.get('elasticsearch')}")
            else:
                self.print_test("Health endpoint", False, f"Unexpected response: {data}")
        except Exception as e:
            self.print_test("Health endpoint", False, f"Error: {str(e)}")
    
    def test_simple_expansion(self):
        """Test simple query expansion."""
        print("\n📋 Test 2: Simple Query Expansion")
        print("-" * 40)
        print("Query: 'blue thing'")
        
        try:
            response = requests.post(
                f"{self.base_url}/search/intelligent",
                json={"query": "blue thing", "max_results": 5},
                timeout=30
            )
            data = response.json()
            
            if response.status_code == 200:
                self.print_test("Query expansion", True)
                print(f"\n  Original: {data.get('query')}")
                print(f"  Expanded: {data.get('expanded_query')}")
                print(f"  Results: {len(data.get('results', []))} items")
                print(f"  Total: {data.get('total_count')} matches")
            else:
                self.print_test("Query expansion", False, f"Status: {response.status_code}, {data}")
        except Exception as e:
            self.print_test("Query expansion", False, f"Error: {str(e)}")
    
    def test_temporal_strict(self):
        """Test temporal query with strict boundary."""
        print("\n📋 Test 3: Temporal Query - Strict Boundary")
        print("-" * 40)
        print("Query: 'blue book taken yesterday'")
        
        try:
            response = requests.post(
                f"{self.base_url}/search/intelligent",
                json={"query": "blue book taken yesterday", "max_results": 10},
                timeout=30
            )
            data = response.json()
            
            if response.status_code == 200:
                conditions = data.get('conditions_applied', {})
                
                self.print_test("Temporal detection", 
                               conditions.get('basedOnEarliestTime') == True,
                               f"basedOnEarliestTime: {conditions.get('basedOnEarliestTime')}")
                
                self.print_test("Strict boundary", 
                               conditions.get('confidence') == True,
                               f"confidence: {conditions.get('confidence')}")
                
                print(f"\n  Conditions Applied:")
                print(f"    Earliest Time: {conditions.get('earliest_timestamp')}")
                print(f"    Time Window: {conditions.get('time_window_minutes')}")
                print(f"    Reasoning: {conditions.get('reasoning')}")
            else:
                self.print_test("Temporal strict", False, f"Status: {response.status_code}")
        except Exception as e:
            self.print_test("Temporal strict", False, f"Error: {str(e)}")
    
    def test_temporal_loose(self):
        """Test temporal query with loose boundary."""
        print("\n📋 Test 4: Temporal Query - Loose Boundary")
        print("-" * 40)
        print("Query: 'blue thing recently'")
        
        try:
            response = requests.post(
                f"{self.base_url}/search/intelligent",
                json={"query": "blue thing recently", "max_results": 10},
                timeout=30
            )
            data = response.json()
            
            if response.status_code == 200:
                conditions = data.get('conditions_applied', {})
                
                has_time_window = conditions.get('time_window_minutes') is not None
                self.print_test("Time window detection", has_time_window,
                               f"time_window_minutes: {conditions.get('time_window_minutes')}")
                
                print(f"\n  Conditions Applied:")
                print(f"    Earliest Time: {conditions.get('earliest_timestamp')}")
                print(f"    Time Window: {conditions.get('time_window_minutes')} minutes")
                print(f"    Confidence: {conditions.get('confidence')}")
            else:
                self.print_test("Temporal loose", False, f"Status: {response.status_code}")
        except Exception as e:
            self.print_test("Temporal loose", False, f"Error: {str(e)}")
    
    def test_non_temporal(self):
        """Test non-temporal query."""
        print("\n📋 Test 5: Non-Temporal Query")
        print("-" * 40)
        print("Query: 'red bag'")
        
        try:
            response = requests.post(
                f"{self.base_url}/search/intelligent",
                json={"query": "red bag", "max_results": 10},
                timeout=30
            )
            data = response.json()
            
            if response.status_code == 200:
                conditions = data.get('conditions_applied', {})
                
                self.print_test("Non-temporal handling",
                               conditions.get('basedOnEarliestTime') == False,
                               f"basedOnEarliestTime: {conditions.get('basedOnEarliestTime')}")
                
                print(f"\n  Expanded Query: {data.get('expanded_query')}")
            else:
                self.print_test("Non-temporal", False, f"Status: {response.status_code}")
        except Exception as e:
            self.print_test("Non-temporal", False, f"Error: {str(e)}")
    
    def test_complex_query(self):
        """Test complex query with multiple factors."""
        print("\n📋 Test 6: Complex Query")
        print("-" * 40)
        print("Query: 'stolen blue backpack last night'")
        
        try:
            response = requests.post(
                f"{self.base_url}/search/intelligent",
                json={"query": "stolen blue backpack last night", "max_results": 10},
                timeout=30
            )
            data = response.json()
            
            if response.status_code == 200:
                self.print_test("Complex query processing", True)
                
                print(f"\n  Original: {data.get('query')}")
                print(f"  Expanded: {data.get('expanded_query')}")
                print(f"\n  Conditions:")
                conditions = data.get('conditions_applied', {})
                print(f"    Temporal: {conditions.get('basedOnEarliestTime')}")
                print(f"    Confidence: {conditions.get('confidence')}")
                print(f"    Reasoning: {conditions.get('reasoning')}")
                
                # Check likelihood scores
                if data.get('results'):
                    scores = [r['likelihood_score'] for r in data['results']]
                    print(f"\n  Likelihood Scores: min={min(scores)}, max={max(scores)}, avg={sum(scores)/len(scores):.1f}")
            else:
                self.print_test("Complex query", False, f"Status: {response.status_code}")
        except Exception as e:
            self.print_test("Complex query", False, f"Error: {str(e)}")
    
    def test_validation(self):
        """Test request validation."""
        print("\n📋 Test 7: Request Validation")
        print("-" * 40)
        
        # Test empty query
        print("Test 7a: Empty query")
        try:
            response = requests.post(
                f"{self.base_url}/search/intelligent",
                json={"query": "", "max_results": 10},
                timeout=30
            )
            
            self.print_test("Empty query validation",
                           response.status_code == 400,
                           f"Status: {response.status_code}")
        except Exception as e:
            self.print_test("Empty query validation", False, f"Error: {str(e)}")
        
        # Test invalid max_results
        print("\nTest 7b: Invalid max_results (>200)")
        try:
            response = requests.post(
                f"{self.base_url}/search/intelligent",
                json={"query": "test", "max_results": 250},
                timeout=30
            )

            self.print_test("max_results validation",
                           response.status_code == 422,
                           f"Status: {response.status_code}")
        except Exception as e:
            self.print_test("max_results validation", False, f"Error: {str(e)}")
    
    def run_all_tests(self):
        """Run all tests and print summary."""
        self.print_header("🧪 Intelligent Search Endpoint Test Suite")
        print(f"Base URL: {self.base_url}\n")
        
        # Run tests
        self.test_health()
        self.test_simple_expansion()
        self.test_temporal_strict()
        self.test_temporal_loose()
        self.test_non_temporal()
        self.test_complex_query()
        self.test_validation()
        
        # Print summary
        self.print_header("📊 Test Summary")
        total = self.passed + self.failed + self.warnings
        print(f"Total Tests: {total}")
        print(f"{Colors.GREEN}Passed: {self.passed}{Colors.NC}")
        print(f"{Colors.RED}Failed: {self.failed}{Colors.NC}")
        print(f"{Colors.YELLOW}Warnings: {self.warnings}{Colors.NC}")
        print(f"\nSuccess Rate: {(self.passed / total * 100) if total > 0 else 0:.1f}%")
        
        return self.failed == 0


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    
    tester = IntelligentSearchTester(base_url)
    success = tester.run_all_tests()
    
    sys.exit(0 if success else 1)
