# data_sources/senate_lda.py
import requests
import urllib.parse
import json
import logging
from datetime import datetime
import re
from collections import defaultdict, Counter

from .base import LobbyingDataSource

# Setup a logger for this module
logger = logging.getLogger('senate_lda')

class SenateLDADataSource(LobbyingDataSource):
    """Senate Lobbying Disclosure Act database data source."""
    
    def __init__(self, api_key, api_base_url="https://lda.senate.gov/api/v1/"):
        self.api_key = api_key.strip() if api_key else ""
        self.api_base_url = api_base_url
        logger.info(f"Initialized Senate LDA data source with API key: {self.api_key[:3]}{'*' * (len(self.api_key) - 3) if self.api_key else 'None'}")
    
    @property
    def source_name(self) -> str:
        return "Senate LDA"
    
    @property
    def government_level(self) -> str:
        return "Federal"
        
    def search_filings(self, query, filters=None, page=1, page_size=25):
        """Search for lobbying filings in the Senate LDA database."""
        if filters is None:
            filters = {}
            
        # Extract filters
        year_from = filters.get('year_from', '')
        year_to = filters.get('year_to', '')
        issue_area = filters.get('issue_area', '')
        agency = filters.get('agency', '')
        amount_min = filters.get('amount_min', '')
        is_person = filters.get('is_person', False)
        
        # Add required headers
        headers = {
            'x-api-key': self.api_key,
            'Accept': 'application/json',
            'User-Agent': 'LobbyingDisclosureApp/1.0'
        }
        
        # Properly encode the query
        encoded_query = urllib.parse.quote(query)
        logger.info(f"Searching for: {query} (is_person={is_person})")
        
        # Try company search first regardless of is_person
        # This could be part of the issue - Senate API might want a different approach
        search_urls = []
        
        # For person searches (lobbying)
        if is_person:
            # Try multiple variants for person search
            search_urls = [
                f"{self.api_base_url}filings/?search={encoded_query}&page={page}&page_size={page_size}",
                f"{self.api_base_url}filings/?lobbyist_name={encoded_query}&page={page}&page_size={page_size}",
                f"{self.api_base_url}lobbyists/?name={encoded_query}"
            ]
        else:
            # For organization/company searches
            search_urls = [
                f"{self.api_base_url}filings/?client_name={encoded_query}&page={page}&page_size={page_size}",
                f"{self.api_base_url}filings/?registrant_name={encoded_query}&page={page}&page_size={page_size}",
                f"{self.api_base_url}filings/?search={encoded_query}&page={page}&page_size={page_size}",
                f"{self.api_base_url}clients/?name={encoded_query}",
                f"{self.api_base_url}registrants/?name={encoded_query}"
            ]
        
        # Add year filters to all URLs if specified
        if year_from or year_to:
            for i in range(len(search_urls)):
                if "?" in search_urls[i]:
                    if year_from and "filing_year__gte" not in search_urls[i]:
                        search_urls[i] += f"&filing_year__gte={year_from}"
                    if year_to and "filing_year__lte" not in search_urls[i]:
                        search_urls[i] += f"&filing_year__lte={year_to}"
        
        # Add direct entity search as fallback (important for organizations like Goldman Sachs)
        if not is_person:
            # Add direct entity lookup - sometimes needed for exact names
            search_urls.append(f"{self.api_base_url}registrants/search/?name={encoded_query}")
            search_urls.append(f"{self.api_base_url}clients/search/?name={encoded_query}")
        
        # Debug all URLs we'll be trying
        logger.info(f"Will try {len(search_urls)} different search URL patterns")
        for i, url in enumerate(search_urls):
            logger.info(f"Search URL option {i+1}: {url}")
        
        response = None
        successful_url = None
        
        try:
            # Try each URL in sequence
            for search_url in search_urls:
                try:
                    # Make API request with additional debugging
                    logger.info(f"Making API request to: {search_url}")
                    response = requests.get(search_url, headers=headers, timeout=30)
                    status_code = response.status_code
                    
                    # Debug response
                    if status_code == 200:
                        logger.info(f"Successful response from URL: {search_url}")
                        successful_url = search_url
                        break
                    else:
                        # Log error details
                        logger.warning(f"API request failed with status {status_code} for URL: {search_url}")
                        logger.warning(f"Response content: {response.text[:300]}")
                except requests.RequestException as e:
                    logger.warning(f"Request exception for URL {search_url}: {str(e)}")
                    continue
            
            # If all attempts failed
            if not successful_url:
                logger.error("All API search attempts failed")
                if response:
                    error_detail = f"Last status code: {response.status_code}, Response: {response.text[:200]}"
                    logger.error(error_detail)
                    return [], 0, {"total_pages": 0}, f"API search failed: {error_detail}"
                else:
                    return [], 0, {"total_pages": 0}, "Failed to connect to any API endpoints"
            
            # Process successful response
            try:
                data = response.json()
                logger.info(f"Successfully parsed JSON response from {successful_url}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON: {str(e)}")
                return [], 0, {"total_pages": 0}, f"Failed to decode API response: {str(e)}"
            
            # Check data format and extract results
            count = 0
            results = []
            
            # Debug the response structure
            if isinstance(data, dict):
                logger.info(f"Response is a dictionary with keys: {', '.join(data.keys())}")
            elif isinstance(data, list):
                logger.info(f"Response is a list with {len(data)} items")
            else:
                logger.info(f"Response is a {type(data)}")
            
            if isinstance(data, dict) and "results" in data:
                # Standard format with results array
                count = data.get("count", 0)
                results_data = data.get("results", [])
                logger.info(f"Found {count} results in API response")
                
                # Process each filing in the results
                for filing in results_data:
                    filing_data = self._process_filing(filing)
                    
                    # Apply additional filters if specified
                    if self._should_include_filing(filing_data, year_from, year_to, issue_area, agency, amount_min):
                        results.append(filing_data)
                    
            elif isinstance(data, list):
                # Direct list of results
                count = len(data)
                logger.info(f"Found {count} results (list format) in API response")
                
                for filing in data:
                    filing_data = self._process_filing(filing)
                    
                    # Apply additional filters if specified
                    if self._should_include_filing(filing_data, year_from, year_to, issue_area, agency, amount_min):
                        results.append(filing_data)
            else:
                # Unexpected format
                logger.error(f"Unknown API response format: {type(data)}")
                return [], 0, {"total_pages": 0}, "Unknown API response format"
            
            # If this was an entity search (clients or registrants endpoint)
            # then we need to fetch the actual filings
            if any(endpoint in successful_url for endpoint in ["clients/", "registrants/", "lobbyists/"]):
                logger.info(f"Processing entity search results to find related filings")
                entity_filings = []
                
                # This determines if we're dealing with client, registrant or lobbyist
                entity_type = None
                if "clients/" in successful_url:
                    entity_type = "client"
                elif "registrants/" in successful_url:
                    entity_type = "registrant" 
                elif "lobbyists/" in successful_url:
                    entity_type = "lobbyist"
                
                # Limit to first 5 entities to avoid too many requests
                entity_limit = min(5, len(data))
                logger.info(f"Will process first {entity_limit} entities from {entity_type} search")
                
                for entity in data[:entity_limit]:
                    if isinstance(entity, dict) and "id" in entity:
                        entity_id = entity.get("id")
                        entity_name = entity.get("name", "Unknown")
                        logger.info(f"Fetching filings for {entity_type} '{entity_name}' (ID: {entity_id})")
                        
                        # Get filings for this entity
                        filings_url = f"{self.api_base_url}filings/?{entity_type}={entity_id}&page=1&page_size={page_size}"
                        try:
                            filings_response = requests.get(filings_url, headers=headers, timeout=30)
                            if filings_response.status_code == 200:
                                filings_data = filings_response.json()
                                logger.info(f"Got response for {entity_type} filings request")
                                
                                if isinstance(filings_data, dict) and "results" in filings_data:
                                    count = filings_data.get("count", 0)
                                    logger.info(f"Found {count} filings for {entity_type} '{entity_name}'")
                                    
                                    for filing in filings_data.get("results", []):
                                        filing_data = self._process_filing(filing)
                                        if self._should_include_filing(filing_data, year_from, year_to, issue_area, agency, amount_min):
                                            entity_filings.append(filing_data)
                                else:
                                    logger.warning(f"Unexpected response format for {entity_type} filings")
                            else:
                                logger.warning(f"Failed to get filings for {entity_type} {entity_id}: Status {filings_response.status_code}")
                        except Exception as e:
                            logger.error(f"Error fetching filings for {entity_type} {entity_id}: {str(e)}")
                
                # Update results with entity filings
                if entity_filings:
                    logger.info(f"Found {len(entity_filings)} filings from entity search")
                    results = entity_filings
                    count = len(results)
                else:
                    logger.warning(f"No filings found from entity search")
            
            # Update count based on filtered results
            filtered_count = len(results)
            logger.info(f"After filtering, returning {filtered_count} results")
            
            # Calculate pagination details
            total_pages = (filtered_count + page_size - 1) // page_size if filtered_count > 0 else 1
            has_next = page < total_pages
            has_prev = page > 1
            
            pagination = {
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev,
                "next_page": page + 1 if has_next else None,
                "prev_page": page - 1 if has_prev else None,
                "page_range": list(range(max(1, page - 2), min(total_pages + 1, page + 3)))
            }
            
            return results, filtered_count, pagination, None
            
        except requests.RequestException as e:
            error_msg = f"API request error: {str(e)}"
            logger.error(error_msg)
            return [], 0, {"total_pages": 0, "has_next": False, "has_prev": False, 
                       "page_range": list(range(1, 2)), "next_page": None, "prev_page": None}, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return [], 0, {"total_pages": 0, "has_next": False, "has_prev": False, 
                       "page_range": list(range(1, 2)), "next_page": None, "prev_page": None}, error_msg
    
    def get_filing_detail(self, filing_id):
        """Get detailed information about a specific filing."""
        # Add required headers
        headers = {
            'x-api-key': self.api_key,
            'Accept': 'application/json',
            'User-Agent': 'LobbyingDisclosureApp/1.0'
        }
        
        # Make sure filing_id is properly sanitized
        filing_id = str(filing_id).strip()
        logger.info(f"Getting filing detail for ID: {filing_id}")
        
        # Try different URL formats
        urls_to_try = [
            f"{self.api_base_url}filings/{filing_id}/",
            f"{self.api_base_url}filings/{filing_id}",
            f"{self.api_base_url}filings/?id={filing_id}",
            f"{self.api_base_url}filings/?filing_id={filing_id}"
        ]
        
        response = None
        for url in urls_to_try:
            try:
                logger.info(f"Trying URL: {url}")
                response = requests.get(url, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    # Found a working URL format
                    logger.info(f"Successful response from URL: {url}")
                    break
                    
            except requests.RequestException as e:
                logger.warning(f"Request failed for URL {url}: {str(e)}")
                continue
        
        # After trying all URL formats
        if not response or response.status_code != 200:
            logger.error(f"All URL attempts failed for filing ID {filing_id}")
            return None, "Could not retrieve filing details. Please try again later."
        
        try:
            filing = response.json()
            
            # For list responses, extract the first item
            if isinstance(filing, dict) and "results" in filing and filing["results"]:
                filing = filing["results"][0]
            
            # Process the filing to extract and format all available information
            processed_filing = self._process_filing_detail(filing)
            
            # After processing, make an additional request to get lobbyists if they're missing
            if processed_filing and (not processed_filing.get("lobbyists") or not processed_filing.get("lobbying_activities")):
                logger.info(f"Incomplete filing data. Making additional requests for filing ID {filing_id}")
                
                # Try to get additional data from the filing endpoint
                additional_url = f"{self.api_base_url}filings/{filing_id}/"
                try:
                    additional_response = requests.get(additional_url, headers=headers, timeout=15)
                    if additional_response.status_code == 200:
                        additional_data = additional_response.json()
                        
                        # Update processed filing with additional data
                        enhanced_filing = self._process_filing_detail(additional_data)
                        
                        # Merge the data, preferring the enhanced version for missing fields
                        for key, value in enhanced_filing.items():
                            if key not in processed_filing or not processed_filing[key]:
                                processed_filing[key] = value
                            elif isinstance(value, list) and isinstance(processed_filing[key], list):
                                # Merge lists without duplicates
                                processed_filing[key] = list(set(processed_filing[key] + value))
                except Exception as e:
                    logger.warning(f"Failed to get additional data: {str(e)}")
            
            return processed_filing, None
            
        except requests.RequestException as e:
            error_msg = f"API request error: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
        except ValueError as e:
            error_msg = f"Error parsing response: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return None, error_msg
    
    def fetch_visualization_data(self, query, filters=None):
        """Fetch data for visualizations."""
        if filters is None:
            filters = {}
            
        # Get advanced search parameters
        year_from = filters.get('year_from', '')
        year_to = filters.get('year_to', '')
        issue_area = filters.get('issue_area', '')
        agency = filters.get('agency', '')
        amount_min = filters.get('amount_min', '')
        
        # Fetch all results for the query (we'll use a larger page size)
        results, count, _, error = self.search_filings(
            query, 
            filters=filters,
            page=1, 
            page_size=100
        )
        
        if error or not results:
            return None, error if error else 'No data found'
        
        # Prepare data for visualization
        years_data = defaultdict(int)
        registrants_data = defaultdict(int)
        amounts_data = []
        
        # Extract data from results
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
            if filing.get("amount") and filing["amount"] is not None:
                try:
                    amount = float(filing["amount"])
                    filing_date = filing.get("filing_date", "Unknown")
                    if filing_date != "Unknown":
                        amounts_data.append((filing_date, amount))
                except (ValueError, TypeError):
                    pass
        
        visualization_data = {
            "years_data": dict(years_data),
            "registrants_data": dict(registrants_data),
            "amounts_data": amounts_data
        }
        
        return visualization_data, None
    
    def _should_include_filing(self, filing, year_from=None, year_to=None, issue_area=None, agency=None, amount_min=None):
        """Apply additional filters to determine if a filing should be included in results."""
        # Filter by year range if specified
        if year_from and filing.get("filing_year"):
            try:
                filing_year = str(filing["filing_year"]).strip()
                if filing_year.isdigit() and int(filing_year) < int(year_from):
                    return False
            except (ValueError, TypeError):
                pass
                
        if year_to and filing.get("filing_year"):
            try:
                filing_year = str(filing["filing_year"]).strip()
                if filing_year.isdigit() and int(filing_year) > int(year_to):
                    return False
            except (ValueError, TypeError):
                pass
        
        # Filter by issue area if specified
        if issue_area and filing.get("issues"):
            # Check if the issue area appears in the filing issues text
            if issue_area.lower() not in filing["issues"].lower():
                return False
        
        # Filter by agency if specified
        if agency and filing.get("agencies"):
            # Check if any of the agencies contain the search term
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
        
        # If all filters pass, include the filing
        return True
    
    def _process_filing(self, filing):
        """Process a filing object from the API into a standardized format."""
        # Get filing ID (use empty string if not found)
        filing_id = filing.get("id", "")
        
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
        
        # IMPROVED DATE EXTRACTION
        # First check for date fields in the filing
        filing_date = "Unknown"
        
        # Check standard date fields first
        date_fields_to_check = [
            "received_date", "filing_date", "date", "effective_date", 
            "created", "updated", "modified", "submission_date", "dt_posted"
        ]
        
        # Try standard date formats first
        for date_field in date_fields_to_check:
            if date_field in filing and filing[date_field]:
                date_value = str(filing[date_field])
                try:
                    # Handle ISO format dates (YYYY-MM-DD)
                    if re.match(r'^\d{4}-\d{2}-\d{2}', date_value):
                        date_obj = datetime.strptime(date_value[:10], "%Y-%m-%d")
                        filing_date = date_obj.strftime("%b %d, %Y")
                        break
                except (ValueError, TypeError):
                    continue
        
        # If date still unknown, check every string field for date patterns
        if filing_date == "Unknown":
            for key, value in filing.items():
                if isinstance(value, str) and re.search(r'\d{4}-\d{2}-\d{2}', value):
                    try:
                        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', value)
                        if date_match:
                            date_str = date_match.group(1)
                            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                            filing_date = date_obj.strftime("%b %d, %Y")
                            break
                    except (ValueError, TypeError):
                        continue
                # Also check for other date formats like MM/DD/YYYY
                elif isinstance(value, str) and re.search(r'\d{1,2}/\d{1,2}/\d{4}', value):
                    try:
                        date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', value)
                        if date_match:
                            date_str = date_match.group(1)
                            date_obj = datetime.strptime(date_str, "%m/%d/%Y")
                            filing_date = date_obj.strftime("%b %d, %Y")
                            break
                    except (ValueError, TypeError):
                        continue
        
        # Extract client information from various formats
        client_name = "Unknown"
        if "client" in filing:
            if isinstance(filing["client"], dict) and "name" in filing["client"]:
                client_name = filing["client"]["name"]
            elif isinstance(filing["client"], str):
                client_name = filing["client"]
        elif "client_name" in filing:
            client_name = filing["client_name"]
        
        # Extract registrant information from various formats
        registrant_name = "Unknown"
        if "registrant" in filing:
            if isinstance(filing["registrant"], dict) and "name" in filing["registrant"]:
                registrant_name = filing["registrant"]["name"]
            elif isinstance(filing["registrant"], str):
                registrant_name = filing["registrant"]
        elif "registrant_name" in filing:
            registrant_name = filing["registrant_name"]
        
        # Extract lobbyists with improved handling
        lobbyists = []
        if "lobbyists" in filing and filing["lobbyists"]:
            if isinstance(filing["lobbyists"], list):
                # List of strings or list of objects
                for item in filing["lobbyists"]:
                    if isinstance(item, str):
                        lobbyists.append(item)
                    elif isinstance(item, dict):
                        # Check multiple fields that might contain the name
                        if "name" in item:
                            lobbyists.append(item["name"])
                        elif "lobbyist_name" in item:
                            lobbyists.append(item["lobbyist_name"])
                        elif "first_name" in item and "last_name" in item:
                            lobbyists.append(f"{item['first_name']} {item['last_name']}")
        elif "lobbyist_list" in filing and isinstance(filing["lobbyist_list"], list):
            for item in filing["lobbyist_list"]:
                if isinstance(item, str):
                    lobbyists.append(item)
                elif isinstance(item, dict):
                    if "name" in item:
                        lobbyists.append(item["name"])
                    elif "lobbyist_name" in item:
                        lobbyists.append(item["lobbyist_name"])
                    elif "first_name" in item and "last_name" in item:
                        lobbyists.append(f"{item['first_name']} {item['last_name']}")
        
        # Ensure we don't have empty strings in the lobbyists list
        lobbyists = [lob for lob in lobbyists if lob.strip()]
        
        # Extract issues with multiple fallbacks
        issues_text = ""
        
        # Check direct specific_issues field
        if "specific_issues" in filing and filing["specific_issues"]:
            issues_text = filing["specific_issues"]
        
        # Check lobbying_activities if no specific issues found
        elif "lobbying_activities" in filing and filing["lobbying_activities"]:
            activities = filing["lobbying_activities"]
            issues_list = []
            
            for activity in activities:
                if isinstance(activity, dict):
                    # Check for general issue area
                    if "general_issue_area" in activity and activity["general_issue_area"]:
                        issues_list.append(f"Area: {activity['general_issue_area']}")
                    
                    # Check for specific issues
                    if "specific_issues" in activity and activity["specific_issues"]:
                        issues_list.append(activity["specific_issues"])
            
            if issues_list:
                issues_text = "; ".join(issues_list)
        
        # Check for general_issue_areas field
        elif "general_issue_areas" in filing and filing["general_issue_areas"]:
            if isinstance(filing["general_issue_areas"], list):
                issues_text = "Areas: " + ", ".join(filing["general_issue_areas"])
            else:
                issues_text = f"Area: {filing['general_issue_areas']}"
        
        # Set default if no issues found
        if not issues_text:
            issues_text = "No specific issues provided"
        
        # Extract agencies with improved handling
        agencies = []
        if "covered_agencies" in filing and filing["covered_agencies"]:
            if isinstance(filing["covered_agencies"], list):
                for agency in filing["covered_agencies"]:
                    if isinstance(agency, str):
                        agencies.append(agency)
                    elif isinstance(agency, dict) and "name" in agency:
                        agencies.append(agency["name"])
            elif isinstance(filing["covered_agencies"], str):
                agencies = [a.strip() for a in filing["covered_agencies"].split(',')]
        elif "agencies" in filing and filing["agencies"]:
            if isinstance(filing["agencies"], list):
                for agency in filing["agencies"]:
                    if isinstance(agency, str):
                        agencies.append(agency)
                    elif isinstance(agency, dict) and "name" in agency:
                        agencies.append(agency["name"])
            elif isinstance(filing["agencies"], str):
                agencies = [a.strip() for a in filing["agencies"].split(',')]
        
        # Ensure we don't have empty strings in the agencies list
        agencies = [agency for agency in agencies if agency.strip()]
        
        # Get filing year and period information
        filing_year = ""
        if "filing_year" in filing and filing["filing_year"]:
            filing_year = filing["filing_year"]
        elif "year" in filing and filing["year"]:
            filing_year = filing["year"]
        
        filing_period = ""
        if "period" in filing and filing["period"]:
            filing_period = filing["period"]
        elif "filing_period" in filing and filing["filing_period"]:
            filing_period = filing["filing_period"]
        
        filing_type = ""
        if "filing_type" in filing and filing["filing_type"]:
            filing_type = filing["filing_type"]
        elif "type" in filing and filing["type"]:
            filing_type = filing["type"]
        
        # Get amount with multiple fallbacks
        amount = None
        for amount_field in ["income_amount", "expense_amount", "amount", "lobbying_expenses"]:
            if amount_field in filing and filing[amount_field]:
                try:
                    # Handle different formats (string, number)
                    if isinstance(filing[amount_field], (int, float)):
                        amount = filing[amount_field]
                        break
                    else:
                        # Try to convert string to number
                        clean_amount = str(filing[amount_field]).replace('$', '').replace(',', '')
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
            "period": filing_period,
            "filing_year": filing_year,
            "filing_type": filing_type,
            "source": "Senate LDA"  # Add source information
        }
        
        return filing_data
    
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
        
        # Create lobbying_activities structure if not present
        if "lobbying_activities" not in processed or not processed["lobbying_activities"]:
            processed["lobbying_activities"] = []
            
            # Try to construct from other fields
            if "general_issue_areas" in filing:
                issue_areas = filing["general_issue_areas"]
                if isinstance(issue_areas, list):
                    for issue_area in issue_areas:
                        activity = {
                            "general_issue_area": issue_area,
                            "specific_issues": processed.get("issues", "")
                        }
                        processed["lobbying_activities"].append(activity)
                elif issue_areas:  # If it's a string or other non-list
                    activity = {
                        "general_issue_area": str(issue_areas),
                        "specific_issues": processed.get("issues", "")
                    }
                    processed["lobbying_activities"].append(activity)
            
            # If we still don't have activities but have issues
            if not processed["lobbying_activities"] and processed.get("issues"):
                activity = {
                    "general_issue_area": "Not Specified",
                    "specific_issues": processed.get("issues", "")
                }
                processed["lobbying_activities"].append(activity)
        
        # Add additional fields for detailed view
        for date_field in ["received_date", "effective_date", "termination_date"]:
            if date_field in filing:
                try:
                    date_value = str(filing[date_field])
                    if re.match(r'^\d{4}-\d{2}-\d{2}', date_value):
                        date_obj = datetime.strptime(date_value[:10], "%Y-%m-%d")
                        processed[date_field] = date_obj.strftime("%b %d, %Y")
                except (ValueError, TypeError):
                    processed[date_field] = None
        
        # Make sure we have both income and expense amounts
        if "income_amount" not in processed and processed.get("amount"):
            processed["income_amount"] = processed["amount"]
        
        if "expense_amount" not in processed:
            processed["expense_amount"] = None
        
        # Ensure consistent structure for covered_agencies
        if "covered_agencies" not in processed:
            processed["covered_agencies"] = processed.get("agencies", [])
        
        # Make sure specific_issues field exists
        if "specific_issues" not in processed:
            processed["specific_issues"] = processed.get("issues", "No specific issues provided")
        
        return processed