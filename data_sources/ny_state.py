# data_sources/ny_state.py
import requests
import json
from datetime import datetime
import re
import logging
import time
from .base import LobbyingDataSource

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('ny_state')

class NYStateLobbyingDataSource(LobbyingDataSource):
    """New York State lobbying disclosure data source.
    
    This class provides methods to search and retrieve lobbying disclosure data
    from the New York State Ethics Commission's disclosure database.
    """
    
    def __init__(self, base_url="https://onlineapps.jcope.ny.gov/LobbyWatch/"):
        """Initialize the NY State data source.
        
        Args:
            base_url (str): Base URL for the NY State Ethics Commission website
        """
        self.base_url = base_url
        self.api_url = f"{self.base_url}api/"
        self.search_url = f"{self.api_url}Filings/SearchFilings"
        self.detail_url = f"{self.api_url}Filings/GetFilingDetails"
        
        # Define headers for requests
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': self.base_url,
            'Referer': self.base_url,
        }
        
        # Initialize session for connection pooling
        self.session = requests.Session()
    
    @property
    def source_name(self) -> str:
        """Return the name of this data source."""
        return "NY State Ethics Commission"
    
    @property
    def government_level(self) -> str:
        """Return the level of government (Federal, State, Local)."""
        return "State"
    
    def _make_api_request(self, url, payload, method="POST", retries=3, timeout=30):
        """Make an API request with retry mechanism.
        
        Args:
            url (str): API endpoint URL
            payload (dict): Request payload
            method (str): HTTP method (GET or POST)
            retries (int): Number of retry attempts
            timeout (int): Request timeout in seconds
            
        Returns:
            tuple: (response_data, error)
        """
        for attempt in range(retries):
            try:
                if method.upper() == "GET":
                    response = self.session.get(
                        url,
                        headers=self.headers,
                        params=payload,
                        timeout=timeout
                    )
                else:  # POST
                    response = self.session.post(
                        url,
                        headers=self.headers,
                        data=json.dumps(payload),
                        timeout=timeout
                    )
                
                response.raise_for_status()
                
                # Try to parse JSON response
                try:
                    return response.json(), None
                except ValueError:
                    return None, f"Invalid JSON response: {response.text[:100]}"
                
            except requests.RequestException as e:
                logger.warning(f"API request attempt {attempt+1}/{retries} failed: {str(e)}")
                if attempt == retries - 1:
                    return None, f"API request failed after {retries} attempts: {str(e)}"
                time.sleep(2)  # Wait before retrying
    
    def search_filings(self, query, filters=None, page=1, page_size=25):
        """Search for lobbying filings in the NY State disclosure database.
        
        Args:
            query (str): Search term (person or organization name)
            filters (dict): Additional filters to apply to the search
            page (int): Page number for pagination
            page_size (int): Number of results per page
            
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
        
        try:
            logger.info(f"Searching NY State disclosures for: {query} (is_person={is_person})")
            
            # Prepare search payload
            payload = {
                "PageNumber": page,
                "PageSize": page_size,
                "SortColumn": "FilingYear",
                "SortOrder": "desc",
                "SearchFields": {
                    "PrincipalLobbyistName": query if is_person else "",
                    "ClientName": "" if is_person else query,
                    "FilingYear": year_from if year_from else "",
                    "FilingType": "",
                    "GovernmentLevel": "",
                    "ContractorName": ""
                }
            }
            
            # Add additional filter fields if provided
            if year_to:
                payload["SearchFields"]["FilingYearTo"] = year_to
                
            # Send search request
            data, error = self._make_api_request(self.search_url, payload)
            
            if error:
                return [], 0, {"total_pages": 0}, error
                
            # Parse response
            if not isinstance(data, dict):
                return [], 0, {"total_pages": 0}, "Unexpected API response format"
            
            # Extract filing count
            count = data.get("TotalRecords", 0)
            filing_list = data.get("FilingList", [])
            
            if not isinstance(filing_list, list):
                return [], 0, {"total_pages": 0}, "Invalid filing list format in API response"
            
            results = []
            for filing in filing_list:
                filing_data = {
                    "id": filing.get("FilingId", ""),
                    "client": filing.get("ClientName", "Unknown"),
                    "registrant": filing.get("PrincipalLobbyistName", "Unknown"),
                    "filing_date": filing.get("FilingDate", "Unknown"),
                    "filing_type": filing.get("FilingType", ""),
                    "filing_year": filing.get("FilingYear", ""),
                    "period": filing.get("FilingPeriod", ""),
                    "issues": filing.get("SubjectMatter", "No specific issues provided"),
                    "lobbyists": [filing.get("IndividualLobbyistName", "")] if filing.get("IndividualLobbyistName") else [],
                    "agencies": [filing.get("GovermentEntity", "")] if filing.get("GovermentEntity") else [],
                    "amount": filing.get("TotalExpenses", None),
                    "source": "NY State Ethics Commission"
                }
                
                # Filter by amount if specified
                if amount_min and filing_data["amount"]:
                    try:
                        if float(filing_data["amount"]) < float(amount_min):
                            continue
                    except (ValueError, TypeError):
                        logger.warning(f"Could not convert amount to float: {filing_data['amount']}")
                
                # Filter by issue area if specified
                if issue_area and filing_data["issues"]:
                    if issue_area.lower() not in filing_data["issues"].lower():
                        continue
                
                # Filter by agency if specified
                if agency and filing_data["agencies"]:
                    agency_match = False
                    for filing_agency in filing_data["agencies"]:
                        if agency.lower() in filing_agency.lower():
                            agency_match = True
                            break
                    
                    if not agency_match:
                        continue
                
                results.append(filing_data)
            
            # Calculate pagination details
            total_pages = (count + page_size - 1) // page_size if count > 0 else 1
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
            
            return results, count, pagination, None
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return [], 0, {"total_pages": 0}, error_msg
    
    def get_filing_detail(self, filing_id):
        """Get detailed information about a specific filing.
        
        Args:
            filing_id (str): The unique identifier for the filing
            
        Returns:
            tuple: (filing_data, error)
        """
        try:
            logger.info(f"Getting NY State filing detail for ID: {filing_id}")
            
            # Prepare request payload
            payload = {
                "filingId": filing_id
            }
            
            # Send detail request
            data, error = self._make_api_request(self.detail_url, payload)
            
            if error:
                return None, error
            
            # Parse response
            if not data or not isinstance(data, dict):
                return None, "Invalid or empty filing detail response"
            
            # Build detailed filing object
            filing_detail = {
                "id": filing_id,
                "client": {
                    "name": data.get("ClientName", "Unknown"),
                    "address": data.get("ClientAddress", ""),
                    "description": data.get("ClientBusinessDescription", ""),
                    "type": data.get("ClientType", "")
                },
                "registrant": {
                    "name": data.get("LobbyistName", "Unknown"),
                    "address": data.get("LobbyistAddress", ""),
                    "type": data.get("LobbyistType", "")
                },
                "filing_date": data.get("DateSubmitted", "Unknown"),
                "filing_type": data.get("FilingType", ""),
                "filing_year": data.get("FilingYear", ""),
                "period": data.get("FilingPeriod", ""),
                "contract_start": data.get("ContractStartDate", ""),
                "contract_end": data.get("ContractEndDate", ""),
                "amount": data.get("TotalExpenses", None),
                "compensation": data.get("TotalCompensation", None),
                "reimbursed_expenses": data.get("TotalReimbursedExpenses", None),
                "lobbying_activities": [],
                "source": "NY State Ethics Commission"
            }
            
            # Extract lobbyists
            lobbyists = []
            if "IndividualLobbyists" in data and isinstance(data["IndividualLobbyists"], list):
                for lobbyist in data["IndividualLobbyists"]:
                    lobbyists.append(lobbyist.get("LobbyistName", ""))
            filing_detail["lobbyists"] = lobbyists
            
            # Extract lobbying activities
            activities = []
            if "LobbyingActivities" in data and isinstance(data["LobbyingActivities"], list):
                for activity in data["LobbyingActivities"]:
                    act_data = {
                        "general_issue_area": activity.get("FocusOfLobbyingDescription", ""),
                        "specific_issues": activity.get("SubjectMatter", ""),
                        "agencies": [agency.get("GovermentEntity", "") for agency in activity.get("GovermentEntities", [])]
                    }
                    activities.append(act_data)
            filing_detail["lobbying_activities"] = activities
            
            # Extract issues from activities if available
            if not activities:
                filing_detail["issues"] = data.get("SubjectMatter", "No specific issues provided")
            else:
                issues = []
                for activity in activities:
                    if activity["specific_issues"]:
                        issues.append(activity["specific_issues"])
                filing_detail["issues"] = "; ".join(issues) if issues else "No specific issues provided"
            
            # Extract agencies from activities if available
            agencies = []
            if "GovermentEntities" in data and isinstance(data["GovermentEntities"], list):
                for entity in data["GovermentEntities"]:
                    agency_name = entity.get("GovermentEntity", "")
                    if agency_name:
                        agencies.append(agency_name)
            filing_detail["agencies"] = agencies
            
            return filing_detail, None
            
        except Exception as e:
            error_msg = f"Unexpected error retrieving filing detail: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return None, error_msg
    
    def fetch_visualization_data(self, query, filters=None):
        """Fetch data for visualizations.
        
        Args:
            query (str): Search term (person or organization name)
            filters (dict): Additional filters to apply to the search
            
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
            years_data = {}
            registrants_data = {}
            amounts_data = []
            
            # Process results
            for filing in results:
                # Track filing years
                if filing.get("filing_year"):
                    year = str(filing["filing_year"])
                    years_data[year] = years_data.get(year, 0) + 1
                
                # Track registrants
                if filing.get("registrant"):
                    reg_name = filing["registrant"]
                    registrants_data[reg_name] = registrants_data.get(reg_name, 0) + 1
                
                # Track amounts
                if filing.get("amount") and filing.get("filing_date"):
                    try:
                        amount = float(filing["amount"])
                        amounts_data.append((filing["filing_date"], amount))
                    except (ValueError, TypeError):
                        pass
            
            visualization_data = {
                "years_data": years_data,
                "registrants_data": registrants_data,
                "amounts_data": amounts_data
            }
            
            return visualization_data, None
            
        except Exception as e:
            error_msg = f"Unexpected error generating visualization data: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return None, error_msg