#!/usr/bin/env python3
"""
Senate LDA API Diagnostic Tool

This script helps diagnose why the Senate LDA API might not be returning
all expected results. It tests multiple search methods and logs detailed
information about each request and response.

How to use:
1. Make sure your .env file has the LDA_API_KEY set
2. Run this script from the command line: python lda_api_diagnostic.py
3. Enter a search query when prompted
4. Review the detailed results
"""

import os
import sys
import json
import requests
import logging
import time
from collections import defaultdict
from datetime import datetime
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("lda_api_diagnostic.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('lda_api_diagnostic')

# Load environment variables
load_dotenv()
API_KEY = os.getenv("LDA_API_KEY")

def print_separator(title=""):
    """Print a separator line with an optional title"""
    width = 80
    if title:
        print(f"\n{'=' * 5} {title} {'=' * (width - 7 - len(title))}")
    else:
        print(f"\n{'=' * width}")

def test_api_connection():
    """Test basic API connectivity and credentials"""
    if not API_KEY:
        logger.error("API key not found in environment variables")
        print("\n❌ API key not found in environment variables. Check your .env file.")
        return False
    
    print(f"\n🔑 Using API Key: {API_KEY[:5]}{'*' * 6}")
    
    headers = {
        'x-api-key': API_KEY,
        'Accept': 'application/json',
        'User-Agent': 'LobbyingDisclosureDiagnostic/1.0'
    }
    
    # Try a simple request
    url = "https://lda.senate.gov/api/v1/filings/?filing_year=2023&page=1&page_size=5"
    
    try:
        print(f"\n⏳ Testing API connection to: {url}")
        
        response = requests.get(url, headers=headers, timeout=30)
        print(f"Response status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            count = data.get("count", 0)
            print(f"✅ Connection successful! Found {count} filings for 2023.")
            return True
        else:
            print(f"\n❌ API request failed with status code: {response.status_code}")
            print(f"Error response: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"\n❌ Connection error: {str(e)}")
        return False

def test_all_search_methods(query, page_size=25):
    """
    Test all possible search methods for the query and log detailed results
    
    This function attempts multiple search patterns that are present in the codebase:
    - Direct search patterns from the main app code
    - Patterns from the improved implementation
    - Patterns from the test script
    """
    if not API_KEY:
        print("\n❌ API key not found. Cannot perform search tests.")
        return False
    
    headers = {
        'x-api-key': API_KEY,
        'Accept': 'application/json',
        'User-Agent': 'LobbyingDisclosureDiagnostic/1.0'
    }
    
    # All possible search patterns to test
    search_patterns = [
        # Basic search patterns
        {"name": "General Search", "url": f"https://lda.senate.gov/api/v1/filings/?search={query}&page=1&page_size={page_size}"},
        {"name": "Client Name", "url": f"https://lda.senate.gov/api/v1/filings/?client_name={query}&page=1&page_size={page_size}"},
        {"name": "Registrant Name", "url": f"https://lda.senate.gov/api/v1/filings/?registrant_name={query}&page=1&page_size={page_size}"},
        
        # Entity search patterns
        {"name": "Client Entity", "url": f"https://lda.senate.gov/api/v1/clients/search/?name={query}"},
        {"name": "Registrant Entity", "url": f"https://lda.senate.gov/api/v1/registrants/search/?name={query}"},
        {"name": "Lobbyist Name", "url": f"https://lda.senate.gov/api/v1/filings/?lobbyist_name={query}&page=1&page_size={page_size}"},
        {"name": "Lobbyist Entity", "url": f"https://lda.senate.gov/api/v1/lobbyists/?name={query}"},
        
        # Additional patterns 
        {"name": "Filing Year 2023", "url": f"https://lda.senate.gov/api/v1/filings/?search={query}&filing_year=2023&page=1&page_size={page_size}"},
        {"name": "Filing Year 2022", "url": f"https://lda.senate.gov/api/v1/filings/?search={query}&filing_year=2022&page=1&page_size={page_size}"},
        {"name": "Filing Year 2023 (Client)", "url": f"https://lda.senate.gov/api/v1/filings/?client_name={query}&filing_year=2023&page=1&page_size={page_size}"},
        {"name": "Filing Year 2023 (Registrant)", "url": f"https://lda.senate.gov/api/v1/filings/?registrant_name={query}&filing_year=2023&page=1&page_size={page_size}"}
    ]
    
    print_separator(f"Testing All Search Methods for '{query}'")
    logger.info(f"Testing all search methods for: '{query}'")
    
    results_summary = []
    entity_ids = {}  # Store entity IDs for secondary requests
    successful_methods = []
    best_method = {"name": None, "count": 0}
    
    # First pass: Test all direct search methods
    for method in search_patterns:
        try:
            print(f"\n⏳ Trying {method['name']} method...")
            logger.info(f"Testing method: {method['name']} - URL: {method['url']}")
            
            start_time = time.time()
            response = requests.get(method["url"], headers=headers, timeout=30)
            elapsed_time = time.time() - start_time
            
            print(f"Response status code: {response.status_code} (in {elapsed_time:.2f}s)")
            logger.info(f"Response status: {response.status_code}, Time: {elapsed_time:.2f}s")
            
            if response.status_code == 200:
                data = response.json()
                
                # Handle different response formats
                result_count = 0
                entity_count = 0
                results_preview = None
                
                if isinstance(data, dict) and "results" in data:
                    # Standard format with results array and count
                    result_count = data.get("count", 0)
                    results = data.get("results", [])
                    results_preview = results[:3] if results else []
                    print(f"✅ Success! Found {result_count} results.")
                    logger.info(f"Found {result_count} results with method: {method['name']}")
                    
                    # When this is a better result than what we've seen so far
                    if result_count > best_method["count"]:
                        best_method = {"name": method["name"], "count": result_count, "url": method["url"]}
                    
                elif isinstance(data, list):
                    # Direct list of entities
                    entity_count = len(data)
                    print(f"✅ Success! Found {entity_count} entities.")
                    logger.info(f"Found {entity_count} entities with method: {method['name']}")
                    
                    # Store entity IDs for secondary requests
                    if entity_count > 0:
                        if "client" in method["url"].lower():
                            entity_ids["clients"] = [entity.get("id") for entity in data[:5] if isinstance(entity, dict) and "id" in entity]
                        elif "registrant" in method["url"].lower():
                            entity_ids["registrants"] = [entity.get("id") for entity in data[:5] if isinstance(entity, dict) and "id" in entity]
                        elif "lobbyist" in method["url"].lower():
                            entity_ids["lobbyists"] = [entity.get("id") for entity in data[:5] if isinstance(entity, dict) and "id" in entity]
                
                # Track successful methods
                successful_methods.append(method["name"])
                
                # Add to results summary
                results_summary.append({
                    "method": method["name"],
                    "url": method["url"],
                    "status": response.status_code,
                    "time": elapsed_time,
                    "result_count": result_count,
                    "entity_count": entity_count,
                    "results_preview": results_preview
                })
            else:
                print(f"❌ Request failed: {response.text[:100]}")
                logger.warning(f"Request failed: {response.status_code} - {response.text[:100]}")
                
                # Add to results summary even if failed
                results_summary.append({
                    "method": method["name"],
                    "url": method["url"],
                    "status": response.status_code,
                    "time": elapsed_time,
                    "error": response.text[:200]
                })
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            logger.error(f"Error testing method {method['name']}: {str(e)}")
            
            # Add error to results summary
            results_summary.append({
                "method": method["name"],
                "url": method["url"],
                "status": "Error",
                "error": str(e)
            })
    
    # Second pass: For entity searches, get related filings
    print_separator("Testing Entity-Related Filings")
    
    for entity_type, ids in entity_ids.items():
        if not ids:
            continue
            
        print(f"\n⏳ Testing filings for {entity_type}...")
        logger.info(f"Testing filings for {entity_type}: {len(ids)} entities")
        
        # Get parameter name (singular form for API)
        param_name = entity_type[:-1] if entity_type.endswith('s') else entity_type
        
        for i, entity_id in enumerate(ids):
            try:
                secondary_url = f"https://lda.senate.gov/api/v1/filings/?{param_name}={entity_id}&page=1&page_size={page_size}"
                print(f"  Testing {entity_type} ID: {entity_id}")
                logger.info(f"Testing {entity_type} ID: {entity_id} - URL: {secondary_url}")
                
                start_time = time.time()
                response = requests.get(secondary_url, headers=headers, timeout=30)
                elapsed_time = time.time() - start_time
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if isinstance(data, dict) and "results" in data:
                        result_count = data.get("count", 0)
                        print(f"    ✅ Found {result_count} filings")
                        logger.info(f"Found {result_count} filings for {entity_type} ID: {entity_id}")
                        
                        # Add to results summary
                        method_name = f"{entity_type.capitalize()} ID {entity_id}"
                        results_summary.append({
                            "method": method_name,
                            "url": secondary_url,
                            "status": response.status_code,
                            "time": elapsed_time,
                            "result_count": result_count,
                            "entity_count": 0
                        })
                        
                        # When this is a better result than what we've seen so far
                        if result_count > best_method["count"]:
                            best_method = {"name": method_name, "count": result_count, "url": secondary_url}
                else:
                    print(f"    ❌ Request failed: {response.status_code}")
                    logger.warning(f"Request failed for {entity_type} ID {entity_id}: {response.status_code}")
            
            except Exception as e:
                print(f"    ❌ Error: {str(e)}")
                logger.error(f"Error testing {entity_type} ID {entity_id}: {str(e)}")
    
    # Print summary report
    print_separator("SUMMARY REPORT")
    print(f"Query: '{query}'")
    print(f"Successful methods: {len(successful_methods)}/{len(search_patterns)}")
    print(f"Best method: {best_method['name']} with {best_method['count']} results")
    print("\nTop 5 methods by result count:")
    
    # Sort results by count and print top 5
    sorted_results = sorted([r for r in results_summary if "result_count" in r], 
                            key=lambda x: x["result_count"], reverse=True)
    
    for i, result in enumerate(sorted_results[:5], 1):
        print(f"{i}. {result['method']}: {result['result_count']} results")
    
    # Save detailed JSON report
    report_file = f"lda_api_diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump({
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "best_method": best_method,
            "results": results_summary
        }, f, indent=2)
    
    print(f"\nDetailed report saved to: {report_file}")
    return True

def detailed_api_test(url, headers, name="Custom Test"):
    """Run a detailed test on a specific API endpoint with verbose logging"""
    print_separator(f"Detailed Test: {name}")
    print(f"URL: {url}")
    logger.info(f"Detailed test - {name}: {url}")
    
    try:
        start_time = time.time()
        response = requests.get(url, headers=headers, timeout=30)
        elapsed_time = time.time() - start_time
        
        print(f"Status Code: {response.status_code} (in {elapsed_time:.2f}s)")
        logger.info(f"Response status: {response.status_code}, Time: {elapsed_time:.2f}s")
        
        if response.status_code == 200:
            data = response.json()
            
            # Analyze response structure
            if isinstance(data, dict):
                print(f"Response type: Dictionary with {len(data)} keys")
                print(f"Keys: {', '.join(data.keys())}")
                
                if "count" in data:
                    print(f"Total count: {data['count']}")
                
                if "results" in data:
                    results = data["results"]
                    print(f"Results: List with {len(results)} items")
                    
                    if results:
                        # Analyze first result
                        first = results[0]
                        if isinstance(first, dict):
                            print(f"First result keys: {', '.join(list(first.keys())[:10])}{'...' if len(first.keys()) > 10 else ''}")
                            
                            # Check for client/registrant structure
                            if "client" in first:
                                client = first["client"]
                                if isinstance(client, dict):
                                    print(f"Client data: {json.dumps(client)[:100]}...")
                                else:
                                    print(f"Client data: {client}")
                            
                            if "registrant" in first:
                                registrant = first["registrant"]
                                if isinstance(registrant, dict):
                                    print(f"Registrant data: {json.dumps(registrant)[:100]}...")
                                else:
                                    print(f"Registrant data: {registrant}")
            
            elif isinstance(data, list):
                print(f"Response type: List with {len(data)} items")
                
                if data:
                    # Analyze first item
                    first = data[0]
                    if isinstance(first, dict):
                        print(f"First item keys: {', '.join(list(first.keys())[:10])}{'...' if len(first.keys()) > 10 else ''}")
            
            # Save full response to file for inspection
            response_file = f"{name.replace(' ', '_').lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(response_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"Full response saved to: {response_file}")
            return data
        else:
            print(f"Request failed: {response.text[:200]}")
            logger.warning(f"Request failed: {response.status_code} - {response.text[:200]}")
            return None
    
    except Exception as e:
        print(f"Error: {str(e)}")
        logger.error(f"Error in detailed test {name}: {str(e)}")
        return None

def compare_with_app_logic(query, is_person=False):
    """
    Test the search patterns used in the app's data source classes
    to see if they match the effective patterns found in testing
    """
    headers = {
        'x-api-key': API_KEY,
        'Accept': 'application/json',
        'User-Agent': 'LobbyingDisclosureDiagnostic/1.0'
    }
    
    print_separator("Comparing with App Logic")
    print(f"Query: {query}, Is Person: {is_person}")
    
    # Original Senate LDA patterns
    original_patterns = []
    if is_person:
        original_patterns = [
            f"filings/?search={query}&page=1&page_size=25",
            f"filings/?lobbyist_name={query}&page=1&page_size=25",
            f"lobbyists/?name={query}"
        ]
    else:
        original_patterns = [
            f"filings/?client_name={query}&page=1&page_size=25",
            f"filings/?registrant_name={query}&page=1&page_size=25",
            f"filings/?search={query}&page=1&page_size=25",
            f"clients/?name={query}",
            f"registrants/?name={query}",
            f"registrants/search/?name={query}",
            f"clients/search/?name={query}"
        ]
        
    # Enhanced Senate LDA patterns
    enhanced_patterns = []
    if is_person:
        enhanced_patterns = [
            {
                "endpoint": "filings/",
                "params": {"lobbyist_name": query, "page": 1, "page_size": 25}
            },
            {
                "endpoint": "lobbyists/",
                "params": {"name": query}
            }
        ]
    else:
        enhanced_patterns = [
            {
                "endpoint": "filings/",
                "params": {"client_name": query, "page": 1, "page_size": 25}
            },
            {
                "endpoint": "filings/",
                "params": {"registrant_name": query, "page": 1, "page_size": 25}
            }      
        ]
        
    # Test original patterns
    print("\nTesting Original SenateLDADataSource Patterns:")
    original_results = {}
    
    for pattern in original_patterns:
        url = f"https://lda.senate.gov/api/v1/{pattern}"
        print(f"\n- Testing: {pattern}")
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                count = 0
                
                if isinstance(data, dict) and "count" in data:
                    count = data.get("count", 0)
                    print(f"  ✅ Found {count} results")
                elif isinstance(data, list):
                    count = len(data)
                    print(f"  ✅ Found {count} entities")
                
                original_results[pattern] = count
            else:
                print(f"  ❌ Failed: Status {response.status_code}")
                original_results[pattern] = f"Failed: {response.status_code}"
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            original_results[pattern] = f"Error: {str(e)}"
    
    # Test enhanced patterns
    print("\nTesting Enhanced (improved_senate_lda) Patterns:")
    enhanced_results = {}
    
    for pattern in enhanced_patterns:
        endpoint = pattern["endpoint"]
        params = pattern["params"]
        params_str = "&".join([f"{k}={v}" for k, v in params.items() if not isinstance(v, bool)])
        
        url = f"https://lda.senate.gov/api/v1/{endpoint}?{params_str}"
        print(f"\n- Testing: {endpoint} with {params}")
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                count = 0
                
                if isinstance(data, dict) and "count" in data:
                    count = data.get("count", 0)
                    print(f"  ✅ Found {count} results")
                elif isinstance(data, list):
                    count = len(data)
                    print(f"  ✅ Found {count} entities")
                
                enhanced_results[f"{endpoint} - {params_str}"] = count
            else:
                print(f"  ❌ Failed: Status {response.status_code}")
                enhanced_results[f"{endpoint} - {params_str}"] = f"Failed: {response.status_code}"
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            enhanced_results[f"{endpoint} - {params_str}"] = f"Error: {str(e)}"
    
    # Summary
    print("\nPatterns Summary:")
    print("\n1. Original Patterns:")
    best_original = {"pattern": None, "count": 0}
    for pattern, count in original_results.items():
        if isinstance(count, int) and count > best_original["count"]:
            best_original = {"pattern": pattern, "count": count}
        print(f"  - {pattern}: {count}")
    
    print("\n2. Enhanced Patterns:")
    best_enhanced = {"pattern": None, "count": 0}
    for pattern, count in enhanced_results.items():
        if isinstance(count, int) and count > best_enhanced["count"]:
            best_enhanced = {"pattern": pattern, "count": count}
        print(f"  - {pattern}: {count}")
    
    print("\nBest Original Pattern:", best_original["pattern"], "with", best_original["count"], "results")
    print("Best Enhanced Pattern:", best_enhanced["pattern"], "with", best_enhanced["count"], "results")
    
    # Return the best patterns
    return {
        "original": best_original,
        "enhanced": best_enhanced,
        "all_original": original_results,
        "all_enhanced": enhanced_results
    }

def main():
    """Main diagnostic function"""
    print("\n" + "=" * 80)
    print("  Senate LDA API Diagnostic Tool")
    print("  Use this tool to diagnose issues with search results")
    print("=" * 80)
    
    # Check if we have API key
    if not test_api_connection():
        print("\n❌ Cannot proceed without a working API connection. Please check your API key.")
        return
    
    while True:
        # Get query from user
        query = input("\nEnter a search term (e.g., Google, Apple, Microsoft): ").strip()
        if not query:
            print("Please enter a valid search term.")
            continue
            
        is_person = input("Is this a person name? (y/N): ").lower().startswith('y')
        
        # Run tests
        test_all_search_methods(query)
        
        # Compare with app logic
        compare_with_app_logic(query, is_person)
        
        # Option to run a custom test
        run_custom = input("\nWould you like to run a detailed test on a specific URL? (y/N): ").lower()
        if run_custom.startswith('y'):
            custom_url = input("Enter the full URL to test: ").strip()
            if custom_url:
                headers = {
                    'x-api-key': API_KEY,
                    'Accept': 'application/json',
                    'User-Agent': 'LobbyingDisclosureDiagnostic/1.0'
                }
                detailed_api_test(custom_url, headers, "Custom URL Test")
        
        # Option to continue
        again = input("\nWould you like to test another query? (y/N): ").lower()
        if not again.startswith('y'):
            break
    
    print("\nDiagnostic tool completed. Check the log files and JSON reports for details.")
    print("Good luck troubleshooting the API issues!")

if __name__ == "__main__":
    main()