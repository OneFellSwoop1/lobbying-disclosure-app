# data_sources/nyc.py
import requests
import json
from datetime import datetime
import re
import logging
import time
from .base import LobbyingDataSource

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('nyc')

class NYCLobbyingDataSource(LobbyingDataSource):
    """New York City lobbying disclosure data source.
    
    This class provides methods to search and retrieve lobbying disclosure data
    from the NYC Open Data API for lobbying disclosures.
    """
    
    def __init__(self, base_url="https://marketplace-api.open.nyc.gov/api/records/"):
        """Initialize the NYC data source.
        
        Args:
            base_url (str): Base URL for the NYC Open Data API
        """
        self.base_url = base_url
        self.dataset_id = "7hna-3umq"  # NYC E-Lobbyist dataset ID
        self.search_url = f"{self.base_url}{self.dataset_id}/search"
        
        # Define headers for requests
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        
        # Initialize session for connection pooling
        self.session = requests.Session()
    
    @property
    def source_name(self) -> str:
        """Return the name of this data source."""
        return "NYC Lobbying Bureau"
    
    @property
    def government_level(self) -> str:
        """Return the level of government (Federal, State, Local)."""
        return "Local"
    
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
        """Search for lobbying filings in the NYC disclosure database.
        
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
            logger.info(f"Searching NYC disclosures for: {query} (is_person={is_person})")
            
            # Calculate offset for pagination
            offset = (page - 1) * page_size
            
            # Prepare search query
            search_term = query.lower()
            
            # Build filter conditions
            filter_conditions = []
            
            # Add year range filter
            if year_from:
                filter_conditions.append(f"report_year >= '{year_from}'")
            if year_to:
                filter_conditions.append(f"report_year <= '{year_to}'")
                
            # Add issue area filter
            if issue_area:
                filter_conditions.append(f"subject_matters like '%{issue_area}%'")
                
            # Add agency filter
            if agency:
                filter_conditions.append(f"agency_names like '%{agency}%'")
                
            # Add amount filter
            if amount_min:
                filter_conditions.append(f"compensation_amount >= {amount_min}")
                
            # Build the filter string
            filter_string = " AND ".join(filter_conditions) if filter_conditions else ""
            
            # Prepare search payload
            payload = {
                "offset": offset,
                "limit": page_size,
                "order": "report_year DESC",
                "filters": {},
                "search": {}
            }
            
            # Add search query
            if is_person:
                # Search in lobbyist fields
                payload["search"]["lobbyist_first_name,lobbyist_last_name"] = search_term
            else:
                # Search in client and principal (registrant) fields
                payload["search"]["client_name,principal_name"] = search_term
            
            # Add filter string if exists
            if filter_string:
                payload["filters"]["body"] = filter_string
                
            # Send search request
            data, error = self._make_api_request(self.search_url, payload)
            
            if error:
                return [], 0, {"total_pages": 0}, error
                
            # Calculate total records and process results
            count = data.get("total_count", 0)
            records = data.get("records", [])
            
            if not isinstance(records, list):
                return [], 0, {"total_pages": 0}, "Invalid records format in API response"
            
            results = []
            for record in records:
                record_fields = record.get("fields", {})
                
                # Skip records with missing key fields
                if not record_fields.get("client_name") and not record_fields.get("principal_name"):
                    continue
                
                # Format the lobbyist name
                lobbyist_first = record_fields.get("lobbyist_first_name", "")
                lobbyist_last = record_fields.get("lobbyist_last_name", "")
                lobbyist_name = f"{lobbyist_first} {lobbyist_last}".strip()
                
                # Process agencies (may be comma-separated string)
                agencies = []
                agency_names = record_fields.get("agency_names", "")
                if agency_names:
                    agencies = [agency.strip() for agency in agency_names.split(",") if agency.strip()]
                
                # Extract filing amount
                amount = None
                try:
                    if record_fields.get("compensation_amount") is not None:
                        amount = float(record_fields["compensation_amount"])
                except (ValueError, TypeError):
                    logger.warning(f"Could not convert amount to float: {record_fields.get('compensation_amount')}")
                
                filing_data = {
                    "id": record.get("id", ""),
                    "client": record_fields.get("client_name", "Unknown"),
                    "registrant": record_fields.get("principal_name", "Unknown"),
                    "filing_date": record_fields.get("filing_date", "Unknown"),
                    "filing_type": record_fields.get("filing_type", ""),
                    "filing_year": record_fields.get("report_year", ""),
                    "period": record_fields.get("report_period", ""),
                    "issues": record_fields.get("subject_matters", "No specific issues provided"),
                    "lobbyists": [lobbyist_name] if lobbyist_name else [],
                    "agencies": agencies,
                    "amount": amount,
                    "source": "NYC Lobbying Bureau"
                }
                
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
            logger.info(f"Getting NYC filing detail for ID: {filing_id}")
            
            # Fetch the record by ID
            detail_url = f"{self.base_url}{self.dataset_id}/{filing_id}"
            
            # Make API request
            data, error = self._make_api_request(detail_url, {}, method="GET")
            
            if error:
                return None, error
                
            # Get record fields
            record = data.get("fields", {})
            
            if not record:
                return None, "Filing not found or empty record returned"
            
            # Format the lobbyist name
            lobbyist_first = record.get("lobbyist_first_name", "")
            lobbyist_last = record.get("lobbyist_last_name", "")
            lobbyist_name = f"{lobbyist_first} {lobbyist_last}".strip()
            
            # Process agencies (may be comma-separated string)
            covered_agencies = []
            agency_names = record.get("agency_names", "")
            if agency_names:
                covered_agencies = [agency.strip() for agency in agency_names.split(",") if agency.strip()]
            
            # Extract amounts
            income_amount = None
            expense_amount = None
            
            try:
                if record.get("compensation_amount") is not None:
                    income_amount = float(record["compensation_amount"])
            except (ValueError, TypeError):
                logger.warning(f"Could not convert income amount: {record.get('compensation_amount')}")
                
            try:
                if record.get("exp_reimbursed") is not None:
                    expense_amount = float(record["exp_reimbursed"])
            except (ValueError, TypeError):
                logger.warning(f"Could not convert expense amount: {record.get('exp_reimbursed')}")
            
            # Create filing detail structure
            filing = {
                "id": filing_id,
                "client": {
                    "name": record.get("client_name", "Unknown"),
                    "description": record.get("client_business", ""),
                    "country": "USA",
                    "state": record.get("client_address_state", ""),
                    "client_type": record.get("client_type", "")
                },
                "registrant": {
                    "name": record.get("principal_name", "Unknown"),
                    "description": record.get("principal_business", ""),
                    "country": "USA",
                    "state": record.get("principal_address_state", "")
                },
                "received_date": record.get("filing_date", "Unknown"),
                "filing_year": record.get("report_year", ""),
                "filing_type": record.get("filing_type", ""),
                "period": record.get("report_period", ""),
                "specific_issues": record.get("subject_matters", "No specific issues provided"),
                "lobbyists": [lobbyist_name] if lobbyist_name else [],
                "covered_agencies": covered_agencies,
                "lobbying_activities": [],
                "income_amount": income_amount,
                "expense_amount": expense_amount,
                "source": "NYC Lobbying Bureau"
            }
            
            # Add lobbying activities
            if record.get("subject_matters"):
                activities = record.get("subject_matters").split(";")
                for activity in activities:
                    activity_text = activity.strip()
                    if activity_text:
                        activity_data = {
                            "general_issue_area": "NYC Local Issues",
                            "specific_issues": activity_text
                        }
                        filing["lobbying_activities"].append(activity_data)
            
            return filing, None
                
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return None, error_msg
    
    def fetch_visualization_data(self, query, filters=None):
        """Fetch data for visualizations.
        
        Args:
            query (str): Search term
            filters (dict): Additional filters
            
        Returns:
            tuple: (visualization_data, error)
        """
        if filters is None:
            filters = {}
            
        logger.info(f"Fetching visualization data for query: {query}")
        
        # Fetch all results for the query (using a larger page size)
        results, count, _, error = self.search_filings(
            query, 
            filters=filters,
            page=1, 
            page_size=100  # Get more data for better visualizations
        )
        
        if error or not results:
            return None, error if error else 'No data found'
        
        # Prepare data for visualization
        years_data = {}
        registrants_data = {}
        amounts_data = []
        
        # Extract data from results
        for filing in results:
            # Track filing years
            if filing.get("filing_year"):
                year = filing["filing_year"]
                years_data[year] = years_data.get(year, 0) + 1
            
            # Track registrants
            if filing.get("registrant"):
                registrant = filing["registrant"]
                registrants_data[registrant] = registrants_data.get(registrant, 0) + 1
            
            # Track amounts if available
            if filing.get("amount") and filing["amount"] is not None:
                amount = filing["amount"]
                filing_date = filing.get("filing_date", "Unknown")
                amounts_data.append((filing_date, amount))
        
        visualization_data = {
            "years_data": years_data,
            "registrants_data": registrants_data,
            "amounts_data": amounts_data
        }
        
        return visualization_data, None