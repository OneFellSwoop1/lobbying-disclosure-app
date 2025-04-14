# data_sources/senate_lda.py
import requests
import urllib.parse
import json
from datetime import datetime
import re
from collections import defaultdict, Counter

from .base import LobbyingDataSource

class SenateLDADataSource(LobbyingDataSource):
    """Senate Lobbying Disclosure Act database data source."""
    
    def __init__(self, api_key, api_base_url="https://lda.senate.gov/api/v1/"):
        self.api_key = api_key.strip()
        self.api_base_url = api_base_url
    
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
        
        # Format URLs based on what works with the API
        if is_person:
            # For person searches
            search_url = f"{self.api_base_url}filings/?search={encoded_query}&page={page}&page_size={page_size}"
        else:
            # For company searches
            search_url = f"{self.api_base_url}filings/?client_name={encoded_query}&page={page}&page_size={page_size}"
        
        try:
            # Make the API request
            response = requests.get(search_url, headers=headers, timeout=15)  # Increased timeout for larger results
            status_code = response.status_code
            
            # If first attempt fails, try alternative search methods
            if status_code != 200:
                # List of alternative search URLs to try
                alternative_urls = [
                    f"{self.api_base_url}filings/?search={encoded_query}&page={page}&page_size={page_size}",
                    f"{self.api_base_url}filings/?registrant_name={encoded_query}&page={page}&page_size={page_size}",
                    f"{self.api_base_url}clients/?name={encoded_query}",
                    f"{self.api_base_url}registrants/?name={encoded_query}"
                ]
                
                # Try each alternative
                for alt_url in alternative_urls:
                    response = requests.get(alt_url, headers=headers, timeout=15)
                    status_code = response.status_code
                    
                    if status_code == 200:
                        break
            
            # Check if we got a successful response
            if status_code != 200:
                return [], 0, {"total_pages": 0}, f"API returned status code {status_code}: {response.text[:100]}"
            
            # Parse the response data
            data = response.json()
            
            # Check data format and extract results
            count = 0
            results = []
            
            if isinstance(data, dict) and "results" in data:
                # Standard format with results array
                count = data.get("count", 0)
                results_data = data.get("results", [])
                
                # Process each filing in the results
                for filing in results_data:
                    filing_data = self._process_filing(filing)
                    
                    # Apply additional filters if specified
                    if self._should_include_filing(filing_data, year_from, year_to, issue_area, agency, amount_min):
                        results.append(filing_data)
                    
            elif isinstance(data, list):
                # Direct list of results
                count = len(data)
                
                for filing in data:
                    filing_data = self._process_filing(filing)
                    
                    # Apply additional filters if specified
                    if self._should_include_filing(filing_data, year_from, year_to, issue_area, agency, amount_min):
                        results.append(filing_data)
            else:
                # Unexpected format
                return [], 0, {"total_pages": 0}, "Unknown API response format"
            
            # Update count based on filtered results
            filtered_count = len(results)
            
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
                "page_range": range(max(1, page - 2), min(total_pages + 1, page + 3))
            }
            
            return results, filtered_count, pagination, None
            
        except requests.RequestException as e:
            error_msg = f"API request error: {str(e)}"
            return [], 0, {"total_pages": 0, "has_next": False, "has_prev": False, 
                       "page_range": range(1, 2), "next_page": None, "prev_page": None}, error_msg
    
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
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    # Found a working URL format
                    break
                    
            except requests.RequestException:
                continue
        
        # After trying all URL formats
        if not response or response.status_code != 200:
            return None, "Could not retrieve filing details. Please try again later."
        
        try:
            filing = response.json()
            
            # For list responses, extract the first item
            if isinstance(filing, dict) and "results" in filing and filing["results"]:
                filing = filing["results"][0]
            
            # Process the filing to extract and format all available information
            processed_filing = self._process_filing_detail(filing)
            
            return processed_filing, None
            
        except requests.RequestException as e:
            error_msg = f"API request error: {str(e)}"
            return None, error_msg
        except ValueError as e:
            error_msg = f"Error parsing response: {str(e)}"
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
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
                    year = int(filing["filing_year"])
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
                if int(filing["filing_year"]) < int(year_from):
                    return False
            except (ValueError, TypeError):
                pass
                
        if year_to and filing.get("filing_year"):
            try:
                if int(filing["filing_year"]) > int(year_to):
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
                    elif isinstance(item, dict) and "name" in item:
                        lobbyists.append(item["name"])
            elif isinstance(filing["lobbyists"], str):
                # Handle case where it might be a comma-separated string
                lobbyists = [name.strip() for name in filing["lobbyists"].split(",")]
        
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
        
        # Extract agencies
        agencies = []
        if "covered_agencies" in filing and filing["covered_agencies"]:
            agencies = filing["covered_agencies"]
        elif "agencies" in filing and filing["agencies"]:
            agencies = filing["agencies"]
        
        # Get filing year and period information
        filing_year = ""
        if "filing_year" in filing and filing["filing_year"]:
            filing_year = filing["filing_year"]
        
        filing_period = ""
        if "period" in filing and filing["period"]:
            filing_period = filing["period"]
        
        filing_type = ""
        if "filing_type" in filing and filing["filing_type"]:
            filing_type = filing["filing_type"]
        
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
        
        # Create empty structures for missing data to prevent template errors
        if "client" not in processed:
            processed["client"] = {"name": processed.get("client", "Unknown Client")}
        elif not isinstance(processed["client"], dict):
            processed["client"] = {"name": processed["client"]}
            
        if "registrant" not in processed:
            processed["registrant"] = {"name": processed.get("registrant", "Unknown Registrant")}
        elif not isinstance(processed["registrant"], dict):
            processed["registrant"] = {"name": processed["registrant"]}
            
        # Add default lobbying_activities if not present
        if "lobbying_activities" not in processed:
            processed["lobbying_activities"] = []
            
            # Try to construct from other fields
            if "general_issue_areas" in filing and filing["general_issue_areas"]:
                for issue_area in filing["general_issue_areas"]:
                    activity = {
                        "general_issue_area": issue_area,
                        "specific_issues": processed.get("issues", "")
                    }
                    processed["lobbying_activities"].append(activity)
        
        # Add description fields if missing
        for entity in ["client", "registrant"]:
            if entity in processed and isinstance(processed[entity], dict):
                for field in ["description", "country", "state", "client_type"]:
                    if field not in processed[entity]:
                        processed[entity][field] = None
        
        return processed 