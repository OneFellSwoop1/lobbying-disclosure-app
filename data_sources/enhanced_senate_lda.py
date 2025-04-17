# enhanced_senate_lda.py
"""
Simplified Enhanced Senate LDA data source based on diagnostic results.
This version focuses on the patterns that actually work for the Senate API.
"""

import requests
import urllib.parse
import json
import logging
from datetime import datetime
import re
from collections import defaultdict

# Setup a logger for this module
logger = logging.getLogger('enhanced_senate_lda')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class EnhancedSenateLDADataSource:
    """Enhanced Senate Lobbying Disclosure Act database data source."""
    
    def __init__(self, api_key, api_base_url="https://lda.senate.gov/api/v1/"):
        self.api_key = api_key.strip() if api_key else ""
        self.api_base_url = api_base_url
        self.session = requests.Session()
        self.session.headers.update({
            'x-api-key': self.api_key,
            'Accept': 'application/json',
            'User-Agent': 'LobbyingDisclosureApp/1.0'
        })
        logger.info(f"Initialized Enhanced Senate LDA data source")
    
    @property
    def source_name(self) -> str:
        return "Senate LDA"
    
    @property
    def government_level(self) -> str:
        return "Federal"
    
    def search_filings(self, query, filters=None, page=1, page_size=25, max_pages=5):
        """
        Search for lobbying filings in the Senate LDA database.
        This simplified version uses only the patterns that worked in diagnostics.
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
        
        # Based on diagnostic results, we'll use these two working patterns
        if is_person:
            # For person searches, we don't have a pattern that worked in diagnostics
            # We'll use a generic search with other filter parameters
            search_patterns = [
                f"filings/?filing_year=2023&lobbyist_name={encoded_query}&page={page}&page_size={page_size}",
            ]
        else:
            # For company searches, use client_name and registrant_name as these worked
            search_patterns = [
                f"filings/?client_name={encoded_query}&page={page}&page_size={page_size}",
                f"filings/?registrant_name={encoded_query}&page={page}&page_size={page_size}"
            ]
        
        # Add year filters if provided
        for i in range(len(search_patterns)):
            if year_from and "filing_year__gte" not in search_patterns[i]:
                search_patterns[i] += f"&filing_year__gte={year_from}"
            if year_to and "filing_year__lte" not in search_patterns[i]:
                search_patterns[i] += f"&filing_year__lte={year_to}"
        
        # Try each search pattern
        for pattern in search_patterns:
            try:
                url = f"{self.api_base_url}{pattern}"
                logger.info(f"Trying search pattern: {url}")
                
                response = self.session.get(url, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check if results are found
                    if isinstance(data, dict) and "results" in data:
                        count = data.get("count", 0)
                        results_data = data.get("results", [])
                        logger.info(f"Found {count} results with pattern: {pattern}")
                        
                        # Process each filing
                        for filing in results_data:
                            filing_data = self._process_filing(filing)
                            
                            # Apply additional filters
                            if self._should_include_filing(filing_data, year_from, year_to, issue_area, agency, amount_min):
                                all_results.append(filing_data)
                        
                        # If there are more pages and max_pages > 1, fetch additional pages
                        if count > page_size and max_pages > 1:
                            logger.info(f"Fetching additional pages for pattern: {pattern}")
                            
                            # Calculate total pages
                            total_pages = min((count + page_size - 1) // page_size, max_pages)
                            
                            # Fetch additional pages
                            for p in range(2, total_pages + 1):
                                logger.info(f"Fetching page {p} of {total_pages}")
                                
                                # Update page number in URL
                                page_url = url.replace(f"page={page}", f"page={p}")
                                
                                try:
                                    page_response = self.session.get(page_url, timeout=30)
                                    
                                    if page_response.status_code == 200:
                                        page_data = page_response.json()
                                        page_results = page_data.get("results", [])
                                        
                                        # Process each filing on the page
                                        for filing in page_results:
                                            filing_data = self._process_filing(filing)
                                            
                                            if self._should_include_filing(filing_data, year_from, year_to, issue_area, agency, amount_min):
                                                all_results.append(filing_data)
                                    else:
                                        logger.warning(f"Failed to get page {p}: Status {page_response.status_code}")
                                except Exception as e:
                                    logger.error(f"Error fetching page {p}: {str(e)}")
                else:
                    logger.warning(f"Pattern {pattern} failed with status {response.status_code}: {response.text[:100]}")
                    error_message = f"API request failed for pattern {pattern}: {response.text[:100]}"
            
            except Exception as e:
                logger.error(f"Error with pattern {pattern}: {str(e)}")
                error_message = f"Error with pattern {pattern}: {str(e)}"
        
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
        try:
            unique_results.sort(key=lambda x: self._get_filing_date_for_sorting(x), reverse=True)
        except Exception as e:
            logger.error(f"Error sorting results: {str(e)}")
        
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
        
        return page_results, total_results, pagination, error_message
    
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
    
    def _should_include_filing(self, filing, year_from=None, year_to=None, issue_area=None, agency=None, amount_min=None):
        """Apply additional filters to determine if a filing should be included in results."""
        # Year range filter
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
        
        # Issue area filter
        if issue_area and filing.get("issues"):
            if issue_area.lower() not in filing["issues"].lower():
                return False
        
        # Agency filter
        if agency and filing.get("agencies"):
            agency_matches = False
            for filing_agency in filing["agencies"]:
                if agency.lower() in filing_agency.lower():
                    agency_matches = True
                    break
            
            if not agency_matches:
                return False
        
        # Amount filter
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
        date_fields = ["received_date", "filing_date", "date", "effective_date"]
        
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
            "filing_year": filing_year,
            "filing_type": filing_type,
            "source": "Senate LDA"
        }
        
        return filing_data
    
    # Add stubs for other required methods (to be implemented as needed)
    def get_filing_detail(self, filing_id):
        """Get detailed information about a specific filing."""
        # Implement basic version for now
        headers = {
            'x-api-key': self.api_key,
            'Accept': 'application/json',
            'User-Agent': 'LobbyingDisclosureApp/1.0'
        }
        
        url = f"{self.api_base_url}filings/{filing_id}/"
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                filing = response.json()
                processed_filing = self._process_filing(filing)
                return processed_filing, None
            else:
                return None, f"Could not retrieve filing details. Status: {response.status_code}"
                
        except Exception as e:
            return None, f"Error retrieving filing: {str(e)}"
    
    def fetch_visualization_data(self, query, filters=None):
        """Fetch data for visualizations."""
        # Placeholder to match the original interface
        if filters is None:
            filters = {}
            
        # Get data
        results, count, _, error = self.search_filings(
            query, 
            filters=filters,
            page=1, 
            page_size=100
        )
        
        if error or not results:
            return None, error if error else 'No data found'
        
        # Prepare data for visualization (simple implementation)
        years_data = defaultdict(int)
        registrants_data = defaultdict(int)
        amounts_data = []
        
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