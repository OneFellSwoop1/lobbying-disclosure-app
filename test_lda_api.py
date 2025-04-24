#!/usr/bin/env python3
"""
Test script for the Senate LDA API connection.
This script helps diagnose issues with the LDA API and verify if your API key is working.
"""

import os
import sys
import json
import requests
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('lda_api_test')

# Load environment variables
load_dotenv()
API_KEY = os.getenv("LDA_API_KEY")

def test_api_connection():
    """Test basic API connectivity"""
    if not API_KEY:
        logger.error("❌ API key not found in environment variables")
        print("\n❌ API key not found in environment variables. Check your .env file.")
        return False
    
    print(f"\n🔑 Using API Key: {API_KEY[:5]}{'*' * 6}")
    
    headers = {
        'x-api-key': API_KEY,
        'Accept': 'application/json',
        'User-Agent': 'LobbyingDisclosureTest/1.0'
    }
    
    # Try a simple request with a filter parameter
    url = "https://lda.senate.gov/api/v1/filings/?filing_year=2023&page=1&page_size=5"
    
    try:
        print(f"\n⏳ Testing API connection to: {url}")
        print("Sending request...")
        
        response = requests.get(url, headers=headers, timeout=30)
        print(f"Response status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            count = data.get("count", 0)
            print(f"✅ Connection successful! Found {count} filings for 2023.")
            print("\n📋 First result preview:")
            
            if data.get("results") and len(data["results"]) > 0:
                first_result = data["results"][0]
                # Print limited preview of first result
                print(json.dumps(first_result, indent=2)[:500] + "...")
                
                # Check if we can access client and registrant info
                client = first_result.get("client", {})
                registrant = first_result.get("registrant", {})
                
                if isinstance(client, dict) and "name" in client:
                    print(f"\n✅ Client name found: {client['name']}")
                else:
                    print("\n❌ Client name not found in expected format")
                
                if isinstance(registrant, dict) and "name" in registrant:
                    print(f"✅ Registrant name found: {registrant['name']}")
                else:
                    print("❌ Registrant name not found in expected format")
                
            return True
        else:
            print(f"\n❌ API request failed with status code: {response.status_code}")
            print(f"Error response: {response.text}")
            return False
    except Exception as e:
        print(f"\n❌ Connection error: {str(e)}")
        return False

def test_search_query(query):
    """Test a specific search query"""
    if not API_KEY:
        print("\n❌ API key not found. Cannot perform search test.")
        return False
    
    headers = {
        'x-api-key': API_KEY,
        'Accept': 'application/json',
        'User-Agent': 'LobbyingDisclosureTest/1.0'
    }
    
    # Test different search approaches
    search_methods = [
        {"name": "General Search", "url": f"https://lda.senate.gov/api/v1/filings/?search={query}&page=1&page_size=5"},
        {"name": "Client Name", "url": f"https://lda.senate.gov/api/v1/filings/?client_name={query}&page=1&page_size=5"},
        {"name": "Registrant Name", "url": f"https://lda.senate.gov/api/v1/filings/?registrant_name={query}&page=1&page_size=5"},
        {"name": "Client Entity", "url": f"https://lda.senate.gov/api/v1/clients/search/?name={query}"},
        {"name": "Registrant Entity", "url": f"https://lda.senate.gov/api/v1/registrants/search/?name={query}"}
    ]
    
    print(f"\n🔍 Testing search for: '{query}'")
    
    successful_methods = []
    best_method = None
    max_results = 0
    
    for method in search_methods:
        try:
            print(f"\n⏳ Trying {method['name']} method...")
            response = requests.get(method["url"], headers=headers, timeout=30)
            print(f"Response status code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Handle different response formats
                count = 0
                if isinstance(data, dict) and "count" in data:
                    count = data.get("count", 0)
                    print(f"✅ Success! Found {count} results.")
                    
                    if count > 0 and "results" in data and len(data["results"]) > 0:
                        first_result = data["results"][0]
                        print(f"📋 First result preview (truncated):")
                        print(json.dumps(first_result, indent=2)[:300] + "...")
                
                elif isinstance(data, list):
                    count = len(data)
                    print(f"✅ Success! Found {count} entities.")
                    
                    if count > 0:
                        first_result = data[0]
                        print(f"📋 First result preview (truncated):")
                        print(json.dumps(first_result, indent=2)[:300] + "...")
                
                # Track the best method
                successful_methods.append(method["name"])
                if count > max_results:
                    max_results = count
                    best_method = method["name"]
            else:
                print(f"❌ Request failed: {response.text[:100]}")
        except Exception as e:
            print(f"❌ Error: {str(e)}")
    
    print("\n📊 Search Test Results Summary:")
    print(f"Query: '{query}'")
    print(f"Successful methods: {', '.join(successful_methods) if successful_methods else 'None'}")
    print(f"Best method: {best_method if best_method else 'None'}")
    print(f"Maximum results found: {max_results}")
    
    if not successful_methods:
        print("\n❌ All search methods failed. Check your API key and network connection.")
        return False
    
    print("\n✅ At least one search method succeeded.")
    return True

if __name__ == "__main__":
    print("\n====== Senate LDA API Test Tool ======")
    
    # Test basic connectivity
    connection_ok = test_api_connection()
    
    if connection_ok:
        # Test with a sample query
        print("\n====== Testing Sample Queries ======")
        
        # Let user input a query or use default
        query = input("\nEnter a company/org to search (or press enter for 'Google'): ").strip()
        if not query:
            query = "Google"
        
        test_search_query(query)
        
        # Give option to try another query
        another = input("\nWould you like to test another query? (y/n): ").lower()
        if another.startswith('y'):
            query = input("Enter another company/org to search: ").strip()
            if query:
                test_search_query(query)
    
    print("\n====== Test Complete ======")