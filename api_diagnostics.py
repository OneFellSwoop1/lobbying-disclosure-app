# api_diagnostics.py
"""
This script tests the Senate LDA API connection to diagnose issues 
with result retrieval. It helps identify why our application might not 
be getting the same results as the official website.
"""

import os
import requests
import json
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('api_diagnostics')

# Load environment variables
load_dotenv()
API_KEY = os.getenv("LDA_API_KEY")

def test_api_connection():
    """Test basic API connectivity"""
    if not API_KEY:
        logger.error("API key not found in environment variables")
        return False
    
    headers = {
        'x-api-key': API_KEY,
        'Accept': 'application/json',
        'User-Agent': 'LobbyingDisclosureApp/1.0'
    }
    
    # Try a simple request with a filter parameter as required by the API
    url = "https://lda.senate.gov/api/v1/filings/?filing_year=2023&page=1&page_size=10"
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        logger.info(f"Connection test status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            count = data.get("count", 0)
            logger.info(f"Total filings available: {count}")
            return True
        else:
            logger.error(f"API request failed: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        return False

def compare_search_approaches(query, page_size=25):
    """Compare different search approaches to find the optimal one"""
    headers = {
        'x-api-key': API_KEY,
        'Accept': 'application/json',
        'User-Agent': 'LobbyingDisclosureApp/1.0'
    }
    
    # Different search patterns to try
    search_patterns = [
        f"filings/?search={query}&page=1&page_size={page_size}",
        f"filings/?client_name={query}&page=1&page_size={page_size}",
        f"filings/?registrant_name={query}&page=1&page_size={page_size}",
        f"clients/search/?name={query}",
        f"registrants/search/?name={query}"
    ]
    
    results = []
    
    for pattern in search_patterns:
        url = f"https://lda.senate.gov/api/v1/{pattern}"
        logger.info(f"Trying search pattern: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            logger.info(f"Status code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract count based on response format
                if isinstance(data, dict) and "count" in data:
                    count = data.get("count", 0)
                    results_data = data.get("results", [])
                    logger.info(f"Found {count} results with pattern: {pattern}")
                    
                    # Log first few results for comparison
                    if results_data:
                        logger.info(f"First result preview: {json.dumps(results_data[0], indent=2)[:300]}...")
                        
                    results.append({
                        "pattern": pattern,
                        "count": count,
                        "status": response.status_code
                    })
                elif isinstance(data, list):
                    count = len(data)
                    logger.info(f"Found {count} results (list format) with pattern: {pattern}")
                    
                    # For entity search endpoints, we need to check related filings
                    if "clients/search" in pattern or "registrants/search" in pattern:
                        logger.info("This is an entity search endpoint - need to check filings for each entity")
                        
                    results.append({
                        "pattern": pattern,
                        "count": count,
                        "status": response.status_code
                    })
            else:
                logger.warning(f"Pattern failed with status {response.status_code}: {response.text[:100]}")
                results.append({
                    "pattern": pattern,
                    "count": 0,
                    "status": response.status_code,
                    "error": response.text[:100]
                })
        except Exception as e:
            logger.error(f"Error with pattern {pattern}: {str(e)}")
            results.append({
                "pattern": pattern,
                "count": 0,
                "status": "Error",
                "error": str(e)
            })
    
    # Find best approach
    valid_results = [r for r in results if r["status"] == 200]
    if valid_results:
        best_approach = max(valid_results, key=lambda x: x["count"])
        logger.info(f"Best search approach: {best_approach['pattern']} with {best_approach['count']} results")
    else:
        logger.error("No valid search approaches found")
    
    return results

def suggest_improvements():
    """Analyze issues and suggest improvements to the code"""
    suggestions = [
        "1. Use the most effective search pattern based on the diagnostic results",
        "2. Implement pagination to retrieve all results (not just the first page)",
        "3. Add proper error handling and retry logic for API requests",
        "4. Cache results to improve performance and reduce API calls",
        "5. Add more detailed logging to track API response structures",
        "6. Consider using async requests for better performance"
    ]
    
    for suggestion in suggestions:
        logger.info(f"Suggestion: {suggestion}")
    
    return suggestions

if __name__ == "__main__":
    print("\n=== Senate LDA API Diagnostics ===\n")
    
    # Test basic connectivity
    if test_api_connection():
        print("\n✅ API connection successful\n")
    else:
        print("\n❌ API connection failed\n")
        exit(1)
    
    # Compare search approaches
    print("\n=== Testing search patterns ===\n")
    query = input("Enter a company or person to search (e.g., Microsoft): ")
    results = compare_search_approaches(query)
    
    # Print summary of results
    print("\n=== Search Pattern Results ===\n")
    for result in results:
        status_symbol = "✅" if result["status"] == 200 else "❌"
        print(f"{status_symbol} Pattern: {result['pattern']}")
        print(f"   Results: {result['count']}")
        print(f"   Status: {result['status']}")
        if "error" in result:
            print(f"   Error: {result['error']}")
        print()
    
    # Suggest improvements
    print("\n=== Suggested Improvements ===\n")
    suggestions = suggest_improvements()
    for suggestion in suggestions:
        print(f"• {suggestion}")