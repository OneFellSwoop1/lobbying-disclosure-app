# utils/error_handling.py
"""
Error handling utilities for the Lobbying Disclosure App.
This module provides consistent error handling and user feedback.
"""

import logging
import traceback
from functools import wraps
from flask import flash, redirect, url_for
import requests
import json
from typing import Dict, Any, Tuple, Optional
from datetime import datetime

logger = logging.getLogger('lobbying_app')

class APIError(Exception):
    """Custom exception for API-related errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(self.message)

class DataSourceError(Exception):
    """Custom exception for data source errors"""
    def __init__(self, message, source=None, details=None):
        self.message = message
        self.source = source
        self.details = details
        super().__init__(self.message)

class ValidationError(Exception):
    """Custom exception for input validation errors"""
    def __init__(self, message, field=None):
        self.message = message
        self.field = field
        super().__init__(self.message)

def api_error_handler(f):
    """Decorator to handle API errors in routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except APIError as e:
            logger.error(f"API Error: {e.message} (Status: {e.status_code})")
            if e.response_text:
                logger.error(f"Response: {e.response_text}")
            flash(f"API Error: {e.message}", "error")
            return redirect(url_for('index'))
        except requests.exceptions.RequestException as e:
            logger.error(f"Request Error: {str(e)}")
            flash("Unable to connect to the API. Please try again later.", "error")
            return redirect(url_for('index'))
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            flash("An unexpected error occurred. Please try again.", "error")
            return redirect(url_for('index'))
    return decorated_function

def validate_search_params(params: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate search parameters before making API request
    Returns (is_valid, error_message)
    """
    # Check if any search parameter is provided
    search_params = ['client_name', 'registrant_name', 'lobbyist_name', 'search']
    if not any(params.get(key) for key in search_params):
        # If no search parameter but has filters, add empty search
        if any(params.get(key) for key in ['filing_year__gte', 'filing_year__lte', 'issue_area_code', 'federal_agency_code']):
            params['search'] = ''
        else:
            return False, "Please provide at least one search term"
    
    # Validate year range
    if params.get('filing_year__gte') and params.get('filing_year__lte'):
        try:
            year_from = int(params['filing_year__gte'])
            year_to = int(params['filing_year__lte'])
            current_year = datetime.now().year
            
            if year_from > year_to:
                return False, "Start year must be less than or equal to end year"
            if year_from < 1999:
                return False, "Start year cannot be earlier than 1999"
            if year_to > current_year:
                return False, f"End year cannot be later than {current_year}"
        except ValueError:
            return False, "Invalid year format"
    
    # Validate amount
    if params.get('amount__gte'):
        try:
            amount = float(params['amount__gte'])
            if amount < 0:
                return False, "Amount must be non-negative"
        except ValueError:
            return False, "Invalid amount format"
    
    return True, ""

def handle_api_response(response: requests.Response, context: str = "") -> Dict[str, Any]:
    """
    Handle API response and raise appropriate errors
    Returns parsed JSON response if successful
    """
    try:
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and 'results' in data:
                # Check for empty results with high count (potential API inconsistency)
                if data.get('count', 0) > 0 and len(data.get('results', [])) == 0:
                    logger.warning(f"API inconsistency: count={data.get('count')} but empty results list")
                return data
            elif isinstance(data, list):
                return {'results': data, 'count': len(data)}
            else:
                return {'results': [], 'count': 0}
        
        error_msg = f"API request failed"
        if context:
            error_msg = f"{error_msg} during {context}"
        
        try:
            error_data = response.json()
            error_detail = error_data.get('detail', '')
        except json.JSONDecodeError:
            error_detail = response.text[:200]
        
        if response.status_code == 400:
            # Based on diagnostics, handle specific error cases
            if 'must pass at least one query string parameter' in error_detail.lower():
                logger.info("API requires at least one filter parameter. Adding default filters.")
                # Return empty results instead of error - caller should add filters and retry
                return {'results': [], 'count': 0, 'error': 'missing_filter'}
            elif 'invalid filter' in error_detail.lower():
                # Identify which filter is invalid
                logger.warning(f"Invalid filter in API request: {error_detail}")
                return {'results': [], 'count': 0, 'error': 'invalid_filter', 'detail': error_detail}
            else:
                error_msg = f"{error_msg}: {error_detail or 'Bad request'}"
        elif response.status_code == 401:
            error_msg = f"{error_msg}: Invalid API key"
            logger.error("API authentication failed - check your API key")
        elif response.status_code == 404:
            # For entity searches, 404 just means no results
            if '/search/' in response.url:
                logger.info(f"Entity search returned 404 - this usually means no results: {response.url}")
                return {'results': [], 'count': 0}
            # Handle special cases for specific endpoints based on diagnostics
            elif '/clients/' in response.url or '/registrants/' in response.url:
                logger.info(f"Entity endpoint returned 404 - treating as empty results: {response.url}")
                return {'results': [], 'count': 0}
            else:
                error_msg = f"{error_msg}: Resource not found"
        elif response.status_code == 429:
            error_msg = f"{error_msg}: Rate limit exceeded. Please try again later"
            logger.warning("API rate limit exceeded - implement backoff strategy")
        elif response.status_code >= 500:
            error_msg = f"{error_msg}: Server error. Please try again later"
            logger.error(f"API server error {response.status_code}: {error_detail}")
            # For 5xx errors, return empty results so caller can fall back to mock data
            return {'results': [], 'count': 0, 'error': 'server_error', 'status': response.status_code}
        
        # Log the full URL that caused the error (for debugging)
        logger.error(f"API error for URL: {response.url}")
        
        raise APIError(
            message=error_msg,
            status_code=response.status_code,
            response_text=error_detail
        )
        
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON response from API: {response.text[:200]}")
        raise APIError(
            message=f"Invalid JSON response {context}",
            status_code=response.status_code,
            response_text=response.text[:200]
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"API connection error: {str(e)}")
        raise APIError(
            message=f"Request failed {context}: {str(e)}",
            status_code=getattr(e.response, 'status_code', None),
            response_text=getattr(e.response, 'text', '')[:200]
        )

def diagnose_api_issue(query: str, search_type: str, filters: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    """
    Run comprehensive diagnostic tests on the API to identify why a search might be failing.
    Returns a dictionary with diagnostic information.
    
    Args:
        query: The user's search query
        search_type: The type of search (registrant, client, lobbyist)
        filters: The search filters being used
        api_key: The API key
        
    Returns:
        Dict with diagnostic information and suggested solutions
    """
    base_url = "https://lda.senate.gov/api/v1"
    headers = {
        'x-api-key': api_key,
        'Accept': 'application/json',
        'User-Agent': 'PythonRequestsClient/1.0 (Diagnostic)'
    }
    
    logger.info(f"Running API diagnostics for: {query} (type: {search_type})")
    
    results = {
        'query': query,
        'search_type': search_type,
        'filters': filters,
        'tests': [],
        'issues_found': [],
        'suggestions': []
    }
    
    # Test 1: Try client_name parameter
    try:
        logger.info("Testing client_name parameter")
        client_url = f"{base_url}/filings/?client_name={query}&filing_year={filters.get('filing_year', datetime.now().year)}&limit=5"
        response = requests.get(client_url, headers=headers, timeout=30)
        
        client_test = {
            'name': 'client_name',
            'url': client_url,
            'status': response.status_code
        }
        
        if response.status_code == 200:
            data = response.json()
            client_test['count'] = data.get('count', 0)
            client_test['result'] = 'success' if client_test['count'] > 0 else 'no_results'
            
            if client_test['count'] > 0 and search_type != 'client':
                results['suggestions'].append(f"Try searching for '{query}' as a client instead of {search_type}")
        else:
            client_test['result'] = 'error'
            client_test['error'] = response.text[:200]
        
        results['tests'].append(client_test)
    except Exception as e:
        logger.error(f"Error in client name test: {str(e)}")
        results['tests'].append({
            'name': 'client_name',
            'result': 'exception',
            'error': str(e)
        })
    
    # Test 2: Try registrant_name parameter
    try:
        logger.info("Testing registrant_name parameter")
        registrant_url = f"{base_url}/filings/?registrant_name={query}&filing_year={filters.get('filing_year', datetime.now().year)}&limit=5"
        response = requests.get(registrant_url, headers=headers, timeout=30)
        
        registrant_test = {
            'name': 'registrant_name',
            'url': registrant_url,
            'status': response.status_code
        }
        
        if response.status_code == 200:
            data = response.json()
            registrant_test['count'] = data.get('count', 0)
            registrant_test['result'] = 'success' if registrant_test['count'] > 0 else 'no_results'
            
            if registrant_test['count'] > 0 and search_type != 'registrant':
                results['suggestions'].append(f"Try searching for '{query}' as a registrant instead of {search_type}")
        else:
            registrant_test['result'] = 'error'
            registrant_test['error'] = response.text[:200]
        
        results['tests'].append(registrant_test)
    except Exception as e:
        logger.error(f"Error in registrant name test: {str(e)}")
        results['tests'].append({
            'name': 'registrant_name',
            'result': 'exception',
            'error': str(e)
        })
    
    # Test 3: Try different year filters
    current_year = datetime.now().year
    for year in range(current_year, current_year - 3, -1):
        if year == filters.get('filing_year'):
            continue  # Skip the year we're already testing
            
        try:
            logger.info(f"Testing year filter: {year}")
            test_url = f"{base_url}/filings/?"
            
            if search_type == 'client':
                test_url += f"client_name={query}"
            elif search_type == 'registrant':
                test_url += f"registrant_name={query}"
            else:
                test_url += f"client_name={query}"  # Default to client
                
            test_url += f"&filing_year={year}&limit=5"
            
            response = requests.get(test_url, headers=headers, timeout=30)
            
            year_test = {
                'name': f'year_{year}',
                'url': test_url,
                'status': response.status_code
            }
            
            if response.status_code == 200:
                data = response.json()
                year_test['count'] = data.get('count', 0)
                year_test['result'] = 'success' if year_test['count'] > 0 else 'no_results'
                
                if year_test['count'] > 0 and year != filters.get('filing_year'):
                    results['suggestions'].append(f"Try searching in year {year} instead of {filters.get('filing_year')}")
            else:
                year_test['result'] = 'error'
                year_test['error'] = response.text[:200]
            
            results['tests'].append(year_test)
        except Exception as e:
            logger.error(f"Error in year {year} test: {str(e)}")
            results['tests'].append({
                'name': f'year_{year}',
                'result': 'exception',
                'error': str(e)
            })
    
    # Test 4: Try with variations of the query
    variations = []
    
    # Remove "Inc", "Corp", etc.
    suffixes = [" Inc", " Inc.", " Corp", " Corp.", " LLC", " Company", " Co", " Co.", " Ltd", " Ltd."]
    for suffix in suffixes:
        if query.endswith(suffix):
            variations.append(query[:-len(suffix)].strip())
            break
    
    # Try without "The" prefix
    if query.lower().startswith('the '):
        variations.append(query[4:])
    
    # Test each variation
    for variation in variations:
        try:
            logger.info(f"Testing query variation: {variation}")
            test_url = f"{base_url}/filings/?"
            
            if search_type == 'client':
                test_url += f"client_name={variation}"
            elif search_type == 'registrant':
                test_url += f"registrant_name={variation}"
            else:
                test_url += f"client_name={variation}"  # Default to client
                
            test_url += f"&filing_year={filters.get('filing_year', datetime.now().year)}&limit=5"
            
            response = requests.get(test_url, headers=headers, timeout=30)
            
            variation_test = {
                'name': f'variation_{variation}',
                'url': test_url,
                'status': response.status_code
            }
            
            if response.status_code == 200:
                data = response.json()
                variation_test['count'] = data.get('count', 0)
                variation_test['result'] = 'success' if variation_test['count'] > 0 else 'no_results'
                
                if variation_test['count'] > 0:
                    results['suggestions'].append(f"Try searching for '{variation}' instead of '{query}'")
            else:
                variation_test['result'] = 'error'
                variation_test['error'] = response.text[:200]
            
            results['tests'].append(variation_test)
        except Exception as e:
            logger.error(f"Error in variation test for {variation}: {str(e)}")
            results['tests'].append({
                'name': f'variation_{variation}',
                'result': 'exception',
                'error': str(e)
            })
    
    # Analyze results and identify issues
    successful_tests = [test for test in results['tests'] if test['result'] == 'success']
    
    if not successful_tests:
        results['issues_found'].append("No successful search variations found")
        results['suggestions'].append("Consider using mock data for this query")
    
    # Log the diagnostic summary
    logger.info(f"API Diagnostics completed for '{query}'. Issues found: {len(results['issues_found'])}, Suggestions: {len(results['suggestions'])}")
    
    return results