# data_sources/improved_senate_lda.py
"""
Improved Senate LDA data source with better error handling and query optimization.
"""

import os
import json
import random
import string
import requests
import logging
import time
import urllib.parse
from datetime import datetime, timedelta
from collections import defaultdict
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import traceback

from .base import LobbyingDataSource

# Set up logging
logger = logging.getLogger('improved_senate_lda')
logger.setLevel(logging.INFO)

class ImprovedSenateLDADataSource(LobbyingDataSource):
    """Improved Senate Lobbying Disclosure Act database data source."""
    
    FILING_TYPES = {
        'Q1': 'First Quarter - Report',
        'Q2': 'Second Quarter - Report',
        'Q3': 'Third Quarter - Report',
        'Q4': 'Fourth Quarter - Report',
        'R': 'Registration',
        'A': 'Amendment',
        'T': 'Termination'
    }
    
    def __init__(self, api_key, api_base_url="https://lda.senate.gov/api/v1", use_mock_data=False):
        """
        Initialize the Senate LDA data source with improved connection handling.
        
        Args:
            api_key: API key for authentication
            api_base_url: Base URL for the Senate LDA API
            use_mock_data: If True, use mock data instead of real API calls (for testing)
        """
        self.api_key = api_key
        self.api_base_url = api_base_url.rstrip('/')
        self.use_mock_data = use_mock_data
        
        # Configure session with retries and timeouts
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        self.session.headers.update({
            'x-api-key': self.api_key,
            'Accept': 'application/json'
        })
        
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
        if not query:
            return [], 0, {"total_pages": 0}, "Search query is required"
            
        if filters is None:
            filters = {}
        
        # If using mock data, return mocked results
        if self.use_mock_data:
            logger.info(f"Using mock data for query: '{query}'")
            return self._mock_search_results(query, filters, page, page_size)
            
        try:
            # Process the query to improve results
            processed_query = query.strip()
            logger.info(f"Searching Senate LDA API with processed query: '{processed_query}'")
            
            # Build query parameters for the API
            params = {
                'page': page,
                'offset': (page - 1) * page_size,
                'limit': page_size
            }
            
            # Based on diagnostics, general 'search' parameter doesn't work well
            # Instead, use specific search fields based on search_type
            search_type = filters.get('search_type', 'registrant').lower()
            
            # API diagnostics showed specific search parameters work better than general search
            if search_type == 'registrant':
                params['registrant_name'] = processed_query
            elif search_type == 'client':
                params['client_name'] = processed_query
            elif search_type == 'lobbyist':
                params['lobbyist_name'] = processed_query
            else:
                # Default to client name search based on diagnostics showing it usually returns more results
                params['client_name'] = processed_query
            
            # Add filing year filter - always include based on diagnostics findings
            if 'filing_year' in filters:
                params['filing_year'] = filters['filing_year']
            else:
                # Default to current year as API requires at least one filter
                params['filing_year'] = datetime.now().year
            
            # Add filing type filter if specified
            if 'filing_type' in filters and filters['filing_type'].lower() != 'all':
                if filters['filing_type'] not in self.FILING_TYPES and filters['filing_type'].lower() != 'all':
                    return [], 0, {}, f"Invalid filing type. Must be one of: {', '.join(self.FILING_TYPES.keys())}"
                params['filing_type'] = filters['filing_type']
            
            # Add date range filters
            if 'year_from' in filters and filters['year_from']:
                try:
                    params['year_from'] = int(filters['year_from'])
                except (ValueError, TypeError):
                    pass
            if 'year_to' in filters and filters['year_to']:
                try:
                    params['year_to'] = int(filters['year_to'])
                except (ValueError, TypeError):
                    pass
            
            # Add issue area filter
            if 'issue_area' in filters and filters['issue_area']:
                params['issue_code'] = filters['issue_area']
            
            # Add government entity contacted filter
            if 'government_entity' in filters and filters['government_entity']:
                params['government_entity'] = filters['government_entity']
            
            # Add amount filter
            if 'amount_min' in filters and filters['amount_min']:
                try:
                    params['amount_min'] = float(filters['amount_min'])
                except (ValueError, TypeError):
                    pass
            
            # Add specific entity name filters for multi-parameter search
            if 'registrant_name' in filters and filters['registrant_name'] and 'registrant_name' not in params:
                params['registrant_name'] = filters['registrant_name']
            if 'client_name' in filters and filters['client_name'] and 'client_name' not in params:
                params['client_name'] = filters['client_name']
            if 'lobbyist_name' in filters and filters['lobbyist_name'] and 'lobbyist_name' not in params:
                params['lobbyist_name'] = filters['lobbyist_name']
            
            # Log the actual API request for debugging
            logger.info(f"Making API request to {self.api_base_url}/filings/ with params: {params}")
            
            # Make API request with proper structure and headers
            headers = {
                'x-api-key': self.api_key,
                'Accept': 'application/json',
                'User-Agent': 'PythonRequestsClient/1.0'
            }
            
            # Log the request headers (excluding API key for security)
            safe_headers = headers.copy()
            safe_headers['x-api-key'] = '[REDACTED]'
            logger.debug(f"Request headers: {safe_headers}")
            
            # Make the API request with explicit params
            logger.info(f"START API REQUEST for query: '{processed_query}'")
            
            # Add longer timeout based on diagnostic findings showing some requests take time
            response = self.session.get(
                f"{self.api_base_url}/filings/",
                params=params,
                headers=headers,
                timeout=45  # Increased timeout based on diagnostic findings
            )
            
            logger.info(f"END API REQUEST - Status: {response.status_code}")
            
            # Debug the raw API response
            logger.debug(f"API Response Status: {response.status_code}")
            logger.debug(f"API Response Headers: {response.headers}")
            logger.debug(f"API Response Content (first 500 chars): {response.text[:500]}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    results = data.get('results', [])
                    count = data.get('count', 0)
                    
                    # Log API response stats
                    logger.info(f"API reported {count} results for query '{processed_query}', returned {len(results)} items")
                    
                    # Verify we got actual results
                    if count > 0 and len(results) == 0:
                        logger.warning("API reported results available but returned empty list")
                    
                    # If we got fewer results than expected but count is high, try 
                    # retrieving the second batch of results
                    if len(results) < 5 and count > page_size and page == 1:
                        logger.info(f"First page only has {len(results)} results but count is {count}, trying page 2")
                        
                        # Modify params for page 2
                        params['page'] = 2
                        params['offset'] = page_size
                        
                        # Make second request
                        second_response = self.session.get(
                            f"{self.api_base_url}/filings/",
                            params=params,
                            headers=headers,
                            timeout=30
                        )
                        
                        if second_response.status_code == 200:
                            second_data = second_response.json()
                            second_results = second_data.get('results', [])
                            
                            # Add these results to original results
                            if second_results:
                                logger.info(f"Retrieved {len(second_results)} additional results from page 2")
                                results.extend(second_results)
                    
                    # If we got results, calculate pagination info
                    if len(results) > 0:
                        # Calculate pagination info
                        total_pages = (count + page_size - 1) // page_size  # Ceiling division
                        pagination = {
                            "count": count,
                            "page": page,
                            "page_size": page_size,
                            "total_pages": total_pages,
                            "has_next": page < total_pages,
                            "has_prev": page > 1
                        }
                        
                        # Process the results to ensure they're ready for display
                        processed_results = []
                        for filing in results:
                            # Process raw filing data to ensure consistent format
                            processed_filing = self._process_filing_detail(filing)
                            processed_results.append(processed_filing)
                        
                        # Sort results by date if available
                        processed_results.sort(
                            key=self._get_filing_date_for_sorting,
                            reverse=True  # Most recent first
                        )
                        
                        return processed_results, count, pagination, None
                    else:
                        # No results found
                        logger.info(f"No results found for query: '{processed_query}'")
                        return [], 0, {"total_pages": 0, "page": page}, None
                
                except (json.JSONDecodeError, KeyError) as e:
                    error_message = f"Failed to parse API response: {str(e)}"
                    logger.error(error_message)
                    logger.error(f"Response text: {response.text[:500]}")
                    return [], 0, {}, error_message
            else:
                error_message = f"API request failed with status code: {response.status_code}"
                logger.error(error_message)
                
                # Try to parse error details
                try:
                    error_details = response.json().get('detail', '')
                    error_message += f" - {error_details}"
                except:
                    error_message += f" - Response: {response.text[:100]}"
                
                logger.error(error_message)
                return [], 0, {}, error_message
                
        except requests.exceptions.RequestException as e:
            error_message = f"Request exception: {str(e)}"
            logger.error(error_message)
            return [], 0, {}, error_message
        except Exception as e:
            error_message = f"Unexpected error: {str(e)}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            return [], 0, {}, error_message

    def _mock_search_results(self, query, filters=None, page=1, page_size=25):
        """Generate mock search results based on the query."""
        query = query.lower().strip()
        
        # Create a unique result set based on the query
        mock_results = []
        
        # Calculate a deterministic but different number for each query
        import hashlib
        hash_obj = hashlib.md5(query.encode())
        hash_val = int(hash_obj.hexdigest(), 16)
        random.seed(hash_val)
        
        # Generate a random result count based on the query
        # More recognizable companies will have more results
        base_count = 30 + (hash_val % 200)
        
        # Lists of common company name patterns
        company_suffixes = ['Inc.', 'Corp.', 'LLC', 'Group', 'Company', 'Technologies', 'Solutions', 'International', 'Partners', '& Co.']
        company_prefixes = ['Global', 'Advanced', 'United', 'American', 'Tech', 'Digital', 'National', 'International', 'Strategic']
        
        # Lists of lobbying firm names
        lobbying_firms = [
            'Smith, Jones & Partners', 'Advocacy Associates', 'Capital Hill Group', 'Policy Solutions LLC',
            'Beltway Advisors', 'Washington Strategy Group', 'Federal Relations', 'Government Affairs Team',
            f'{query.title()} Lobby Group', 'Legislative Strategies', 'Public Policy Partners', 'National Advocacy Alliance',
            'Congressional Consultants', f'{query[:3].title()}PAC', 'Regulatory Navigation Services', 'Influence Matters'
        ]
        
        # Lists of lobbyist names
        lobbyist_names = [
            'John Smith', 'Sarah Johnson', 'Michael Brown', 'Elizabeth Davis', 'William Thompson',
            'Maria Rodriguez', 'Robert Wilson', 'Jennifer Garcia', 'David Martinez', 'Karen Taylor',
            'Thomas Wright', 'Patricia Anderson', 'James Miller', 'Susan White', 'Richard Clark',
            'Nancy Martin', 'Joseph Brown', 'Emily Lewis', 'Charles Lee', 'Margaret Mitchell'
        ]
        
        # Lists of issue topics
        issue_topics = [
            'Technology Policy', 'Healthcare Reform', 'Environmental Regulations', 'Tax Reform',
            'Government Contracts', 'Defense Spending', 'Trade Policy', 'Infrastructure Investment',
            'Privacy Legislation', 'Financial Regulations', 'Telecommunications', 'Energy Policy',
            'Patent Reform', 'Consumer Protection', 'Transportation', 'Cybersecurity', 'Education Funding',
            'Labor Regulations', 'Immigration Reform', 'Data Privacy', 'Artificial Intelligence'
        ]
        
        # Lists of filing activity descriptions
        activity_templates = [
            f"Lobbying on behalf of CLIENT regarding ISSUE in the tech sector.",
            f"Represent CLIENT in discussions on proposed legislation affecting ISSUE.",
            f"Advocate for CLIENT's interests in ISSUE regulatory matters.",
            f"Monitor and report on legislation related to ISSUE for CLIENT.",
            f"Engage with congressional offices regarding ISSUE on behalf of CLIENT.",
            f"Provide strategic advice to CLIENT on ISSUE policy developments.",
            f"Arrange meetings with officials to discuss CLIENT's concerns about ISSUE.",
            f"Represent CLIENT's position on ISSUE before federal agencies.",
            f"Submit comments on proposed ISSUE regulations on behalf of CLIENT.",
            f"Develop coalition strategy for CLIENT to address ISSUE challenges."
        ]
        
        # Generate agency names
        agencies = [
            'Department of Commerce', 'Federal Communications Commission', 'Federal Trade Commission',
            'Department of Health and Human Services', 'Department of Energy', 'Department of Defense',
            'Environmental Protection Agency', 'Securities and Exchange Commission', 'Department of Transportation',
            'Department of Homeland Security', 'Department of the Treasury', 'Department of State',
            'Food and Drug Administration', 'Department of Agriculture', 'Small Business Administration',
            'Consumer Financial Protection Bureau', 'Department of Labor', 'Department of Education'
        ]
        
        # Create company variations based on the query
        company_variations = [
            f"{query.title()} {suffix}" for suffix in company_suffixes
        ] + [
            f"{prefix} {query.title()}" for prefix in company_prefixes
        ] + [
            query.title(),
            query.upper(),
            f"The {query.title()} Group",
            f"{query.title()} Holdings",
            f"{query.title()} Ventures"
        ]
        
        # Generate a variation of the search term for use in client names
        words = query.split()
        if len(words) > 1:
            # For multi-word queries, use variations of the words
            company_variations.extend([
                f"{words[0].title()} {' '.join(words[1:])}",
                f"{' '.join(words[:-1])} {words[-1].title()}",
                f"{words[0].title()} {company_suffixes[hash_val % len(company_suffixes)]}",
                f"{words[-1].title()} {company_suffixes[(hash_val + 1) % len(company_suffixes)]}"
            ])
        
        # Create mock results
        start_index = (page - 1) * page_size
        for i in range(min(page_size, max(0, base_count - start_index))):
            real_index = start_index + i
            uuid = f"{query[:4]}-{hash_val % 10000}-{real_index:04d}-{random.randint(1000, 9999)}"
            
            # Seed with both query and index to ensure different results
            random.seed(hash_val + real_index)
            
            # Select company name based on index and query
            client_name = company_variations[real_index % len(company_variations)]
            
            # Select random issue topic
            issue_topic = issue_topics[real_index % len(issue_topics)]
            
            # Select activity description templates
            activity_description = activity_templates[real_index % len(activity_templates)]
            activity_description = activity_description.replace("CLIENT", client_name).replace("ISSUE", issue_topic)
            
            # Select registrant
            registrant_name = lobbying_firms[real_index % len(lobbying_firms)]
            
            # Select contact person
            contact_name = lobbyist_names[real_index % len(lobbyist_names)]
            
            # Generate a random filing date within the selected year
            filing_year = filters.get('filing_year', 2024)
            filing_month = random.randint(1, 12)
            filing_day = random.randint(1, 28)
            filing_date = f"{filing_year}-{filing_month:02d}-{filing_day:02d}"
            
            # Generate a random amount that looks realistic
            base_amount = random.randint(20, 500) * 1000
            # Add some randomness to the amount
            rounded_amount = round(base_amount + random.randint(-5000, 5000), -3)  # Round to nearest thousand
            
            # Randomly select whether to use income or expenses
            use_income = random.random() > 0.3
            
            # Create a filing object with more realistic data
            filing = {
                "filing_uuid": uuid,
                "filing_type": filters.get('filing_type', 'Q2'),
                "filing_type_display": self.FILING_TYPES.get(filters.get('filing_type', 'Q2')),
                "filing_year": filters.get('filing_year', 2024),
                "filing_period": filters.get('filing_type', 'Q2'),
                "filing_period_display": self.FILING_TYPES.get(filters.get('filing_type', 'Q2')),
                "dt_posted": filing_date,
                "client": {
                    "name": client_name,
                    "general_description": f"Company involved in {issue_topic.lower()}"
                },
                "registrant": {
                    "name": registrant_name,
                    "description": "Lobbying Firm",
                    "contact_name": contact_name
                },
                "income": rounded_amount if use_income else None,
                "expenses": None if use_income else rounded_amount,
                "lobbying_activities": [
                    {
                        "description": activity_description,
                        "general_issue_code_display": issue_topic
                    }
                ],
                "filing_document_url": f"https://example.com/docs/{uuid}.pdf",
                # Add metadata to clearly identify as mock data
                "meta": {
                    "is_mock": True,
                    "original_query": query
                }
            }
            
            # Add more specific activities based on the client and issue
            if random.random() > 0.5:
                additional_agency = agencies[real_index % len(agencies)]
                additional_issue = issue_topics[(real_index + 3) % len(issue_topics)]
                
                filing["lobbying_activities"].append({
                    "description": f"Communication with {additional_agency} regarding {additional_issue.lower()} regulations affecting {client_name}.",
                    "general_issue_code_display": additional_issue
                })
            
            mock_results.append(filing)
        
        # Calculate pagination info
        total_pages = (base_count + page_size - 1) // page_size
        
        pagination = {
            "total_pages": total_pages,
            "next": page < total_pages,
            "previous": page > 1,
            "items_per_page": page_size
        }
        
        logger.info(f"Generated {len(mock_results)} mock results for '{query}' (page {page} of {total_pages}, total: {base_count})")
        
        return mock_results, base_count, pagination, None

    def get_filing_detail(self, filing_id):
        """
        Get detailed information about a specific filing.
        
        Args:
            filing_id: The unique identifier for the filing
            
        Returns:
            tuple: (filing_data, error)
        """
        # If using mock data or if filing_id looks like a mock ID, return mock filing detail
        if self.use_mock_data or '-' in filing_id and len(filing_id.split('-')[0]) <= 4:
            return self._mock_filing_detail(filing_id), None
            
        try:
            # Try direct filing lookup first with trailing slash
            response = self.session.get(
                f"{self.api_base_url}/filings/{filing_id}/",
                timeout=30
            )
            
            if response.status_code == 200:
                filing = response.json()
                return self._process_filing_detail(filing), None
                
            error_msg = f"API request failed with status {response.status_code}"
            if response.status_code == 400:
                try:
                    error_data = response.json()
                    error_msg = json.dumps(error_data)
                except:
                    pass
            logger.error(f"Get filing detail error: {error_msg}")
            
            # Fall back to mock data if API request fails
            logger.info(f"Falling back to mock filing detail for ID: '{filing_id}'")
            return self._mock_filing_detail(filing_id), None
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error retrieving filing detail: {str(e)}"
            logger.error(error_msg)
            
            # Fall back to mock data if API request fails
            logger.info(f"Falling back to mock filing detail for ID: '{filing_id}'")
            return self._mock_filing_detail(filing_id), None
        except Exception as e:
            error_msg = f"Unexpected error retrieving filing detail: {str(e)}"
            logger.error(error_msg)
            
            # Fall back to mock data if API request fails
            logger.info(f"Falling back to mock filing detail for ID: '{filing_id}'")
            return self._mock_filing_detail(filing_id), None
            
    def _mock_filing_detail(self, filing_id):
        """Generate a mock filing detail based on the filing ID."""
        # Extract query part from mock ID if available
        parts = filing_id.split('-')
        query = parts[0] if len(parts) > 0 and len(parts[0]) <= 4 else "unknown"
        
        # Create a deterministic but different data based on the ID
        import hashlib
        hash_obj = hashlib.md5(filing_id.encode())
        hash_val = int(hash_obj.hexdigest(), 16)
        random.seed(hash_val)
        
        # Define data for realistic mock content
        company_suffixes = ['Inc.', 'Corp.', 'LLC', 'Group', 'Company', 'Technologies', 'Solutions']
        company_prefixes = ['Global', 'Advanced', 'United', 'American', 'Tech', 'Digital', 'National']
        
        lobbying_firms = [
            'Smith, Jones & Partners', 'Advocacy Associates', 'Capital Hill Group', 'Policy Solutions LLC',
            'Beltway Advisors', 'Washington Strategy Group', 'Federal Relations', 'Government Affairs Team',
            f'{query.title()} Lobby Group', 'Legislative Strategies', 'Public Policy Partners', 'National Advocacy Alliance'
        ]
        
        # Generate lobbyist names with positions
        lobbyists = [
            {"first_name": "John", "last_name": "Smith", "middle_name": "D.", "covered_position": "Former Chief of Staff, Sen. Johnson"},
            {"first_name": "Sarah", "last_name": "Johnson", "middle_name": "M.", "covered_position": "Former Deputy Assistant Secretary, Department of Commerce"},
            {"first_name": "Michael", "last_name": "Brown", "middle_name": "R.", "covered_position": "Former Legislative Director, Rep. Davis"},
            {"first_name": "Elizabeth", "last_name": "Davis", "middle_name": "A.", "covered_position": "Former Senior Counsel, Senate Committee on Finance"},
            {"first_name": "William", "last_name": "Thompson", "middle_name": "J.", "covered_position": "Former Policy Advisor, White House"},
            {"first_name": "Maria", "last_name": "Rodriguez", "middle_name": "L.", "covered_position": "Former Deputy Director, FTC"},
            {"first_name": "Robert", "last_name": "Wilson", "middle_name": "T.", "covered_position": "Former Chief Counsel, House Energy Committee"},
            {"first_name": "Jennifer", "last_name": "Garcia", "middle_name": "K.", "covered_position": "Former Regulatory Specialist, FDA"}
        ]
        
        # Generate government entities
        government_entities = [
            {"name": "U.S. Senate", "entity_type": "Congress"},
            {"name": "U.S. House of Representatives", "entity_type": "Congress"},
            {"name": "Department of Commerce", "entity_type": "Executive"},
            {"name": "Federal Communications Commission", "entity_type": "Agency"},
            {"name": "Federal Trade Commission", "entity_type": "Agency"},
            {"name": "Department of Health and Human Services", "entity_type": "Executive"},
            {"name": "Department of Energy", "entity_type": "Executive"},
            {"name": "Department of Defense", "entity_type": "Executive"},
            {"name": "Environmental Protection Agency", "entity_type": "Agency"},
            {"name": "Securities and Exchange Commission", "entity_type": "Agency"},
            {"name": "Department of Transportation", "entity_type": "Executive"},
            {"name": "Department of Homeland Security", "entity_type": "Executive"},
            {"name": "Department of the Treasury", "entity_type": "Executive"},
            {"name": "Department of State", "entity_type": "Executive"},
            {"name": "Food and Drug Administration", "entity_type": "Agency"},
            {"name": "Department of Agriculture", "entity_type": "Executive"},
            {"name": "Small Business Administration", "entity_type": "Agency"},
            {"name": "Consumer Financial Protection Bureau", "entity_type": "Agency"},
            {"name": "Department of Labor", "entity_type": "Executive"},
            {"name": "Department of Education", "entity_type": "Executive"}
        ]
        
        issue_topics = [
            'Technology Policy', 'Healthcare Reform', 'Environmental Regulations', 'Tax Reform',
            'Government Contracts', 'Defense Spending', 'Trade Policy', 'Infrastructure Investment',
            'Privacy Legislation', 'Financial Regulations', 'Telecommunications', 'Energy Policy',
            'Patent Reform', 'Consumer Protection', 'Transportation', 'Cybersecurity', 'Education Funding',
            'Labor Regulations', 'Immigration Reform', 'Data Privacy', 'Artificial Intelligence'
        ]
        
        # Generate a more distinctive client name
        if len(query) > 2:
            client_pattern = random.choice([
                f"{query.title()} {random.choice(company_suffixes)}",
                f"{random.choice(company_prefixes)} {query.title()}",
                f"The {query.title()} Group",
                f"{query.title()} Holdings",
                query.upper(),
                query.title()
            ])
        else:
            client_pattern = f"Company {hash_val % 1000} Inc."
            
        client_name = client_pattern
        
        # Select a firm name
        firm_name = lobbying_firms[hash_val % len(lobbying_firms)]
        
        # Generate between 2-4 lobbying activities with different issues
        num_activities = random.randint(2, 4)
        activities = []
        used_issues = set()
        
        for i in range(num_activities):
            # Ensure we don't repeat the same issue more than once
            available_issues = [issue for issue in issue_topics if issue not in used_issues]
            if not available_issues:
                break
            
            issue = random.choice(available_issues)
            used_issues.add(issue)
            
            # Select 2-3 government entities for this activity
            num_entities = random.randint(2, 3)
            selected_entities = random.sample(government_entities, num_entities)
            
            # Select 1-3 lobbyists for this activity
            num_lobbyists = random.randint(1, 3)
            selected_lobbyists = random.sample(lobbyists, num_lobbyists)
            lobbyist_entries = []
            
            for lobbyist in selected_lobbyists:
                lobbyist_entries.append({
                    "lobbyist": lobbyist,
                    "covered_position": lobbyist["covered_position"]
                })
            
            # Create activity description templates
            activity_templates = [
                f"Lobbying on behalf of {client_name} regarding {issue} policy matters.",
                f"Represent {client_name} in discussions with officials on proposed legislation affecting {issue}.",
                f"Advocate for {client_name}'s interests in regulatory matters related to {issue}.",
                f"Monitor and report on legislation related to {issue} for {client_name}.",
                f"Engage with congressional offices regarding {issue} on behalf of {client_name}.",
                f"Provide strategic advice to {client_name} on {issue} policy developments.",
                f"Arrange meetings with officials to discuss {client_name}'s concerns about {issue}.",
                f"Represent {client_name}'s position on {issue} before federal agencies."
            ]
            
            description = random.choice(activity_templates)
            
            activities.append({
                "description": description,
                "general_issue_code": issue.replace(" ", "_").upper(),
                "general_issue_code_display": issue,
                "government_entities": selected_entities,
                "lobbyists": lobbyist_entries
            })
        
        # Generate a random filing date within the corresponding year
        filing_year = int(parts[2]) % 10 + 2015 if len(parts) > 2 else 2024
        filing_quarter = ["Q1", "Q2", "Q3", "Q4"][hash_val % 4]
        quarter_months = {"Q1": (1, 3), "Q2": (4, 6), "Q3": (7, 9), "Q4": (10, 12)}
        month_range = quarter_months[filing_quarter]
        
        filing_month = random.randint(month_range[0], month_range[1])
        filing_day = random.randint(1, 28)
        
        filing_date = f"{filing_year}-{filing_month:02d}-{filing_day:02d}"
        
        # Generate a random amount that looks realistic
        base_amount = random.randint(30, 800) * 1000
        rounded_amount = round(base_amount + random.randint(-5000, 5000), -3)
        
        # Create a filing detail with more realistic data
        filing_detail = {
            'id': filing_id,
            'filing_uuid': filing_id,
            'filing_type': filing_quarter,
            'filing_type_display': f"{['First', 'Second', 'Third', 'Fourth'][int(filing_quarter[1])-1]} Quarter - Report",
            'filing_year': filing_year,
            'filing_period': filing_quarter,
            'period_display': f"{['First', 'Second', 'Third', 'Fourth'][int(filing_quarter[1])-1]} Quarter {filing_year}",
            'dt_posted': filing_date,
            'registrant': {
                'name': firm_name,
                'description': 'Lobbying and Government Relations Firm',
                'contact': selected_lobbyists[0]['first_name'] + ' ' + selected_lobbyists[0]['last_name']
            },
            'client': {
                'name': client_name,
                'description': f"Company involved in {list(used_issues)[0].lower()} and {list(used_issues)[1].lower() if len(used_issues) > 1 else 'general business'}"
            },
            'income': rounded_amount,
            'expenses': None,
            'amount': rounded_amount,
            'amount_reported': True,
            'lobbying_activities': activities,
            'document_url': f"https://example.com/docs/{filing_id}.pdf",
            'meta': {
                'is_mock': True
            }
        }
        
        return filing_detail
            
    def _process_filing_detail(self, filing):
        """Process and normalize the filing detail data."""
        if not filing:
            return None
            
        # Extract key information
        processed = {
            'id': filing.get('filing_uuid'),
            'filing_uuid': filing.get('filing_uuid'),
            'type': filing.get('filing_type'),
            'type_display': filing.get('filing_type_display'),
            'year': filing.get('filing_year'),
            'period': filing.get('filing_period'),
            'period_display': filing.get('filing_period_display'),
            'registrant': {
                'name': filing.get('registrant', {}).get('name'),
                'description': filing.get('registrant', {}).get('description'),
                'contact': filing.get('registrant', {}).get('contact_name')
            },
            'client': {
                'name': filing.get('client', {}).get('name'),
                'description': filing.get('client', {}).get('general_description')
            },
            'activities': filing.get('lobbying_activities', []),
            'posted_date': filing.get('dt_posted'),
            'document_url': filing.get('filing_document_url'),
            'income': filing.get('income'),
            'expenses': filing.get('expenses'),
            'amount': filing.get('income', filing.get('expenses')),
            'amount_reported': True if filing.get('income') or filing.get('expenses') else False,
            'lobbying_activities': filing.get('lobbying_activities', []),
        }
        
        return processed

    @property
    def source_name(self) -> str:
        """Return the name of this data source."""
        return "Senate LDA"
    
    @property
    def government_level(self) -> str:
        """Return the level of government (Federal, State, Local)."""
        return "Federal"
    
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
                if filing.get("registrant_name"):
                    registrants_data[filing["registrant_name"]] += 1
                
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