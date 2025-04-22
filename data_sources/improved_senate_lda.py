# data_sources/improved_senate_lda.py
"""
Improved Senate LDA data source with better error handling,
caching, and query optimization based on diagnostic results.
"""

import requests
import urllib.parse
import json
import logging
import time
from datetime import datetime
import re
from collections import defaultdict
from functools import lru_cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base import LobbyingDataSource

# Set up logging
logger = logging.getLogger('improved_senate_lda')
logger.setLevel(logging.INFO)

class ImprovedSenateLDADataSource(LobbyingDataSource):
    """Improved Senate Lobbying Disclosure Act database data source."""
    
    def __init__(self, api_key, api_base_url="https://lda.senate.gov/api/v1/", cache_size=100):
        """
        Initialize the Senate LDA data source with improved connection handling.
        
        Args:
            api_key: The API key for the Senate LDA database
            api_base_url: Base URL for the API
            cache_size: Number of requests to cache
        """
        self.api_key = api_key.strip() if api_key else ""
        self.api_base_url = api_base_url
        self.cache_size = cache_size
        
        # Configure headers
        self.headers = {
            'x-api-key': self.api_key,
            'Accept': 'application/json',
            'User-Agent': 'LobbyingDisclosureApp/1.0'
        }
        
        # Configure retries with exponential backoff
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        
        # Create session with retry adapter
        self.session = requests.Session()
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.headers.update(self.headers)
        
        logger.info(f"Initialized Improved Senate LDA data source with API key: {self.api_key[:3]}{'*' * 6}")
    
    @property
    def source_name(self) -> str:
        """Return the name of this data source."""
        return "Senate LDA"
    
    @property
    def government_level(self) -> str:
        """Return the level of government (Federal, State, Local)."""
        return "Federal"
    
    @lru_cache(maxsize=100)
    def _cached_request(self, url_path, params_str):
        """
        Make an API request with caching.
        
        Args:
            url_path: The API endpoint path
            params_str: JSON string of parameters
            
        Returns:
            The JSON response
        """
        params = json.loads(params_str) if params_str else {}
        full_url = f"{self.api_base_url}{url_path}"
        
        try:
            logger.info(f"Making API request to: {full_url} with params: {params}")
            response = self.session.get(full_url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            if e.response.status_code == 401:
                raise ValueError("API authentication failed. Please check your API key.")
            elif e.response.status_code == 429:
                raise ValueError("API rate limit exceeded. Please try again later.")
            else:
                raise ValueError(f"API request failed with status {e.response.status_code}")
        except requests.exceptions.ConnectionError:
            logger.error("Connection error")
            raise ValueError("Unable to connect to the API. Please check your internet connection.")
        except requests.exceptions.Timeout:
            logger.error("Request timed out")
            raise ValueError("Request timed out. The API server might be slow or unresponsive.")
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON response from API")
            raise ValueError("The API returned an invalid response format.")
        
    def search_filings(self, query, filters=None, page=1, page_size=25):
        """
        Search for lobbying filings in the Senate LDA database.
        
        Args:
            query: Search term (person or organization name)
            filters: Additional filters to apply to the search
            page: Page number for pagination
            page_size: Number of results per page
            
        Returns:
            tuple: (results, count, pagination_info, error)
        """
        if filters is None:
            filters = {}
        
        # Extract filters    
        year_from = filters.get('year_from', '')
        year_to = filters.get('year_to', '')
        issue_area = filters.get('issue_area', '')
        agency = filters.get('agency', '')
        amount_min = filters.get('amount_min', '')
        is_person = filters.get('is_person', False)
        
        # Properly encode the query
        encoded_query = urllib.parse.quote(query)
        logger.info(f"Searching for: {query} (is_person={is_person})")
        
        # Initialize results
        all_results = []
        error_message = None
        
        try:
            # Define search strategies based on query type
            if is_person:
                # For person searches, prioritize lobbyist_name endpoint
                search_strategies = [
                    {
                        "endpoint": "filings/",
                        "params": {"lobbyist_name": query, "page": page, "page_size": page_size}
                    },
                    {
                        "endpoint": "lobbyists/",
                        "params": {"name": query},
                        "requires_second_request": True,
                        "second_endpoint": "filings/",
                        "second_params_key": "lobbyist"
                    }
                ]
            else:
                # For organization searches, try both client and registrant endpoints
                search_strategies = [
                    {
                        "endpoint": "filings/",
                        "params": {"client_name": query, "page": page, "page_size": page_size}
                    },
                    {
                        "endpoint": "filings/",
                        "params": {"registrant_name": query, "page": page, "page_size": page_size}
                    },           
                ]
            
            # Add year filters if specified
            for strategy in search_strategies:
                if year_from:
                    strategy["params"]["filing_year__gte"] = year_from
                if year_to:
                    strategy["params"]["filing_year__lte"] = year_to
            
            # Try each search strategy
            for strategy in search_strategies:
                try:
                    # Convert params to string for caching
                    params_str = json.dumps(strategy["params"])
                    
                    # Make the API request
                    data = self._cached_request(strategy["endpoint"], params_str)
                    
                    # Handle different response formats
                    if isinstance(data, dict) and "results" in data:
                        # Standard results format
                        count = data.get("count", 0)
                        results_data = data.get("results", [])
                        logger.info(f"Found {count} results with endpoint: {strategy['endpoint']}")
                        
                        for filing in results_data:
                            filing_data = self._process_filing(filing)
                            if self._should_include_filing(filing_data, issue_area, agency, amount_min):
                                all_results.append(filing_data)
                    
                    elif isinstance(data, list) and strategy.get("requires_second_request"):
                        # Entity search results - need to fetch related filings
                        entity_count = len(data)
                        logger.info(f"Found {entity_count} entities with endpoint: {strategy['endpoint']}")
                        
                        # Limit to first 5 entities to avoid too many requests
                        for entity in data[:5]:
                            if isinstance(entity, dict) and "id" in entity:
                                entity_id = entity.get("id")
                                second_params = {
                                    strategy["second_params_key"]: entity_id,
                                    "page": 1,
                                    "page_size": 10
                                }
                                
                                if year_from:
                                    second_params["filing_year__gte"] = year_from
                                if year_to:
                                    second_params["filing_year__lte"] = year_to
                                
                                second_params_str = json.dumps(second_params)
                                
                                try:
                                    filings_data = self._cached_request(
                                        strategy["second_endpoint"], 
                                        second_params_str
                                    )
                                    
                                    if isinstance(filings_data, dict) and "results" in filings_data:
                                        filing_count = filings_data.get("count", 0)
                                        logger.info(f"Found {filing_count} filings for entity ID: {entity_id}")
                                        
                                        for filing in filings_data.get("results", []):
                                            filing_data = self._process_filing(filing)
                                            if self._should_include_filing(filing_data, issue_area, agency, amount_min):
                                                all_results.append(filing_data)
                                except Exception as e:
                                    logger.warning(f"Error fetching filings for entity {entity_id}: {str(e)}")
                    
                    elif isinstance(data, list):
                        # Direct list of results
                        logger.info(f"Found {len(data)} results (list format) with endpoint: {strategy['endpoint']}")
                        
                        for filing in data:
                            filing_data = self._process_filing(filing)
                            if self._should_include_filing(filing_data, issue_area, agency, amount_min):
                                all_results.append(filing_data)
                
                except ValueError as e:
                    # Log the error but continue with other strategies
                    logger.warning(f"Error with strategy {strategy['endpoint']}: {str(e)}")
                    if not error_message:
                        error_message = str(e)
                except Exception as e:
                    logger.error(f"Unexpected error with strategy {strategy['endpoint']}: {str(e)}")
                    if not error_message:
                        error_message = f"Error searching filings: {str(e)}"
            
            # Remove duplicate results
            unique_results = []
            seen_ids = set()
            
            for filing in all_results:
                filing_id = filing.get("id", "")
                if filing_id and filing_id not in seen_ids:
                    seen_ids.add(filing_id)
                    unique_results.append(filing)
            
            logger.info(f"Total unique results: {len(unique_results)}")
            
            # Sort results by filing date (most recent first)
            unique_results.sort(key=lambda x: self._get_filing_date_for_sorting(x), reverse=True)
            
            # Calculate pagination details
            total_results = len(unique_results)
            total_pages = (total_results + page_size - 1) // page_size if total_results > 0 else 1
            
            # Slice results for the current page
            start_idx = (page - 1) * page_size
            end_idx = min(start_idx + page_size, total_results)
            
            page_results = unique_results[start_idx:end_idx] if start_idx < total_results else []
            
            pagination = {
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
                "next_page": page + 1 if page < total_pages else None,
                "prev_page": page - 1 if page > 1 else None,
                "page_range": list(range(max(1, page - 2), min(total_pages + 1, page + 3)))
            }
            
            # Return results with any error messages
            return page_results, total_results, pagination, error_message
            
        except Exception as e:
            logger.error(f"Unexpected error in search_filings: {str(e)}")
            return [], 0, {"total_pages": 0}, f"An unexpected error occurred: {str(e)}"
    
    def _get_filing_date_for_sorting(self, filing):
        """Helper to get a date for sorting purposes"""
        try:
            date_str = filing.get("filing_date", "")
            if date_str and date_str != "Unknown":
                return datetime.strptime(date_str, "%b %d, %Y")
            else:
                # Use a default old date for unknown dates
                return datetime(1900, 1, 1)
        except:
            return datetime(1900, 1, 1)
    
    def _should_include_filing(self, filing, issue_area=None, agency=None, amount_min=None):
        """Apply additional filters to determine if a filing should be included in results."""
        # Filter by issue area if specified
        if issue_area and filing.get("issues"):
            if issue_area.lower() not in filing["issues"].lower():
                return False
        
        # Filter by agency if specified
        if agency and filing.get("agencies"):
            agency_matches = False
            for filing_agency in filing["agencies"]:
                if agency.lower() in filing_agency.lower():
                    agency_matches = True
                    break
            
            if not agency_matches:
                return False
        
        # Filter by minimum amount if specified
        if amount_min and filing.get("amount"):
            try:
                min_amount = float(amount_min)
                filing_amount = float(filing["amount"])
                
                if filing_amount < min_amount:
                    return False
            except (ValueError, TypeError):
                pass
        
        # Include filing if it passes all filters
        return True
    
    def _process_filing(self, filing):
        """Process a filing object from the API into a standardized format."""
        # Get filing ID
        filing_id = filing.get("id", filing.get("filing_uuid", ""))
        
        # Handle empty filings
        if not filing:
            return {
                "id": "",
                "filing_date": "Unknown",
                "client": "Unknown",
                "registrant": "Unknown",
                "lobbyists": [],
                "issues": "No information available",
                "agencies": [],
                "amount": None
            }
        
        # Extract date
        filing_date = "Unknown"
        date_fields = ["received_date", "filing_date", "date", "effective_date", "created", "updated"]
        
        for date_field in date_fields:
            if date_field in filing and filing[date_field]:
                date_value = str(filing[date_field])
                try:
                    if re.match(r'^\d{4}-\d{2}-\d{2}', date_value):
                        date_obj = datetime.strptime(date_value[:10], "%Y-%m-%d")
                        filing_date = date_obj.strftime("%b %d, %Y")
                        break
                except (ValueError, TypeError):
                    continue
        
        # Extract client
        client_name = "Unknown"
        if "client" in filing:
            if isinstance(filing["client"], dict) and "name" in filing["client"]:
                client_name = filing["client"]["name"]
            elif isinstance(filing["client"], str):
                client_name = filing["client"]
        elif "client_name" in filing:
            client_name = filing["client_name"]
        
        # Extract registrant
        registrant_name = "Unknown"
        if "registrant" in filing:
            if isinstance(filing["registrant"], dict) and "name" in filing["registrant"]:
                registrant_name = filing["registrant"]["name"]
            elif isinstance(filing["registrant"], str):
                registrant_name = filing["registrant"]
        elif "registrant_name" in filing:
            registrant_name = filing["registrant_name"]
        
        # Extract lobbyists
        lobbyists = []
        if "lobbyists" in filing and filing["lobbyists"]:
            if isinstance(filing["lobbyists"], list):
                for item in filing["lobbyists"]:
                    if isinstance(item, str):
                        lobbyists.append(item)
                    elif isinstance(item, dict):
                        if "name" in item:
                            lobbyists.append(item["name"])
                        elif "lobbyist_name" in item:
                            lobbyists.append(item["lobbyist_name"])
                        elif "first_name" in item and "last_name" in item:
                            lobbyists.append(f"{item['first_name']} {item['last_name']}")
        
        # Extract issues
        issues_text = ""
        if "specific_issues" in filing and filing["specific_issues"]:
            issues_text = filing["specific_issues"]
        elif "lobbying_activities" in filing and filing["lobbying_activities"]:
            issues_list = []
            for activity in filing["lobbying_activities"]:
                if isinstance(activity, dict):
                    if "general_issue_area" in activity and activity["general_issue_area"]:
                        issues_list.append(f"Area: {activity['general_issue_area']}")
                    if "specific_issues" in activity and activity["specific_issues"]:
                        issues_list.append(activity["specific_issues"])
            if issues_list:
                issues_text = "; ".join(issues_list)
        
        if not issues_text:
            issues_text = "No specific issues provided"
        
        # Extract agencies
        agencies = []
        if "covered_agencies" in filing and filing["covered_agencies"]:
            if isinstance(filing["covered_agencies"], list):
                for agency in filing["covered_agencies"]:
                    if isinstance(agency, str):
                        agencies.append(agency)
                    elif isinstance(agency, dict) and "name" in agency:
                        agencies.append(agency["name"])
        
        # Get filing year
        filing_year = ""
        if "filing_year" in filing and filing["filing_year"]:
            filing_year = filing["filing_year"]
        
        # Get filing type
        filing_type = ""
        if "filing_type" in filing and filing["filing_type"]:
            filing_type = filing["filing_type"]
        elif "type" in filing and filing["type"]:
            filing_type = filing["type"]
        
        # Get amount
        amount = None
        for amount_field in ["income_amount", "expense_amount", "amount"]:
            if amount_field in filing and filing[amount_field]:
                try:
                    if isinstance(filing[amount_field], (int, float)):
                        amount = filing[amount_field]
                        break
                    else:
                        # Try to convert string to number
                        clean_amount = str(filing[amount_field]).replace(',', '')
                        if clean_amount.strip():
                            amount = float(clean_amount)
                            break
                except (ValueError, AttributeError):
                    continue
        
        # Create standardized filing data
        filing_data = {
            "id": filing_id,
            "filing_date": filing_date,
            "client": client_name,
            "registrant": registrant_name,
            "lobbyists": lobbyists,
            "issues": issues_text,
            "agencies": agencies,
            "amount": amount,
            "filing_year": filing_year,
            "filing_type": filing_type,
            "source": "Senate LDA"
        }
        
        return filing_data
    
    def get_filing_detail(self, filing_id):
        """
        Get detailed information about a specific filing.
        
        Args:
            filing_id: The unique identifier for the filing
            
        Returns:
            tuple: (filing_data, error)
        """
        try:
            logger.info(f"Getting filing detail for ID: {filing_id}")
            
            # Try direct filing detail endpoint
            params = {"id": filing_id}
            params_str = json.dumps(params)
            
            try:
                # First try the direct filing endpoint
                filing = self._cached_request(f"filings/{filing_id}/", "")
                processed_filing = self._process_filing_detail(filing)
                return processed_filing, None
            except Exception as e:
                logger.warning(f"Direct filing endpoint failed: {str(e)}, trying search endpoint")
                
                # Try search endpoint as fallback
                try:
                    filings_data = self._cached_request("filings/", params_str)
                    
                    if isinstance(filings_data, dict) and "results" in filings_data and filings_data["results"]:
                        filing = filings_data["results"][0]
                        processed_filing = self._process_filing_detail(filing)
                        return processed_filing, None
                    else:
                        return None, "Filing not found"
                except Exception as e2:
                    logger.error(f"Filing search endpoint failed: {str(e2)}")
                    return None, f"Could not retrieve filing: {str(e2)}"
                
        except Exception as e:
            logger.error(f"Unexpected error retrieving filing detail: {str(e)}")
            return None, f"An unexpected error occurred: {str(e)}"
    
    def _process_filing_detail(self, filing):
        """Process a filing for detailed view."""
        # First use the standard processing to get consistent data
        processed = self._process_filing(filing)
        
        # Create deeper client structure
        if "client" in filing and isinstance(filing["client"], dict):
            client_data = filing["client"]
            processed["client"] = {
                "name": client_data.get("name", processed.get("client", "Unknown")),
                "description": client_data.get("general_description", ""),
                "country": client_data.get("country", "USA"),
                "state": client_data.get("state", ""),
                "client_type": client_data.get("client_type", "")
            }
        else:
            processed["client"] = {
                "name": processed.get("client", "Unknown Client"),
                "description": "",
                "country": "USA",
                "state": "",
                "client_type": ""
            }
        
        # Create deeper registrant structure 
        if "registrant" in filing and isinstance(filing["registrant"], dict):
            registrant_data = filing["registrant"]
            processed["registrant"] = {
                "name": registrant_data.get("name", processed.get("registrant", "Unknown")),
                "description": registrant_data.get("general_description", ""),
                "country": registrant_data.get("country", "USA"),
                "state": registrant_data.get("state", "")
            }
        else:
            processed["registrant"] = {
                "name": processed.get("registrant", "Unknown Registrant"),
                "description": "",
                "country": "USA",
                "state": ""
            }
        
        # Extract lobbying activities
        processed["lobbying_activities"] = []
        
        if "lobbying_activities" in filing and filing["lobbying_activities"]:
            activities = filing["lobbying_activities"]
            
            for activity in activities:
                if isinstance(activity, dict):
                    activity_data = {
                        "general_issue_area": activity.get("general_issue_area", "Not specified"),
                        "specific_issues": activity.get("specific_issues", "")
                    }
                    processed["lobbying_activities"].append(activity_data)
        elif "specific_issues" in filing and filing["specific_issues"]:
            # If we only have specific issues but no activities structure
            processed["lobbying_activities"].append({
                "general_issue_area": "General Lobbying",
                "specific_issues": filing["specific_issues"]
            })
        
        # Add additional date fields for detailed view
        for date_field in ["received_date", "effective_date", "termination_date"]:
            if date_field in filing:
                try:
                    date_value = str(filing[date_field])
                    if re.match(r'^\d{4}-\d{2}-\d{2}', date_value):
                        date_obj = datetime.strptime(date_value[:10], "%Y-%m-%d")
                        processed[date_field] = date_obj.strftime("%b %d, %Y")
                except (ValueError, TypeError):
                    processed[date_field] = None
        
        # Add covered agencies list if not already present
        if "covered_agencies" not in processed:
            processed["covered_agencies"] = processed.get("agencies", [])
        
        # Make sure specific_issues field exists
        if "specific_issues" not in processed:
            processed["specific_issues"] = processed.get("issues", "No specific issues provided")
        
        return processed
    
    def fetch_visualization_data(self, query, filters=None):
        """
        Fetch data for visualizations.
        
        Args:
            query: Search term (person or organization name)
            filters: Additional filters to apply to the search
            
        Returns:
            tuple: (visualization_data, error)
        """
        try:
            # Get a larger set of results for visualization
            results, count, _, error = self.search_filings(
                query, 
                filters=filters,
                page=1, 
                page_size=100
            )
            
            if error or not results:
                return None, error if error else "No data found for visualization"
            
            # Prepare data for visualization
            years_data = defaultdict(int)
            registrants_data = defaultdict(int)
            amounts_data = []
            
            # Process results
            for filing in results:
                # Track filing years
                if filing.get("filing_year"):
                    try:
                        year = str(filing["filing_year"]).strip()
                        if year.isdigit():
                            years_data[year] += 1
                    except (ValueError, TypeError):
                        pass
                
                # Track registrants
                if filing.get("registrant"):
                    registrants_data[filing["registrant"]] += 1
                
                # Track amounts if available
                if filing.get("amount") and filing.get("filing_date"):
                    try:
                        amount = float(filing["amount"])
                        amounts_data.append((filing["filing_date"], amount))
                    except (ValueError, TypeError):
                        pass
            
            visualization_data = {
                "years_data": dict(years_data),
                "registrants_data": dict(registrants_data),
                "amounts_data": amounts_data
            }
            
            return visualization_data, None
            
        except Exception as e:
            logger.error(f"Error generating visualization data: {str(e)}")
            return None, f"An error occurred while generating visualization data: {str(e)}"

    def clear_cache(self):
        """Clear the request cache."""
        self._cached_request.cache_clear()
        logger.info("API request cache cleared")