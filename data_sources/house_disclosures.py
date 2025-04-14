# data_sources/house_disclosures.py
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from typing import Dict, List, Any
import time
import urllib.parse

from .base import LobbyingDataSource

class HouseDisclosuresDataSource(LobbyingDataSource):
    """House Office of the Clerk lobbying disclosures data source."""
    
    def __init__(self, base_url="https://disclosurespreview.house.gov/"):
        self.base_url = base_url
        self.search_url = f"{self.base_url}ld/ldxSearchResult.aspx"
        self.detail_url = f"{self.base_url}ld/ldxViewReport.aspx"
        
        # Define headers for requests to mimic a browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    @property
    def source_name(self) -> str:
        return "House Lobbying Disclosures"
    
    @property
    def government_level(self) -> str:
        return "Federal"
        
    def search_filings(self, query, filters=None, page=1, page_size=10):
        """Search for lobbying filings in the House disclosure database."""
        print(f"DEBUG: Starting House search for query: {query}")
        
        # For now, return a clear error message
        error_message = ("The House Clerk website is currently not accessible. "
                        "This may be due to website changes, server issues, or restrictions on automated access. "
                        "We'll continue working on adding this data source.")
        
        return [], 0, {"total_pages": 0}, error_message
    
    def get_filing_detail(self, filing_id):
        """Get detailed information about a specific filing."""
        # Return an error message since we can't access filing details
        error_message = ("Unable to retrieve filing details from the House Clerk website. "
                        "This data source is currently under development.")
        
        return None, error_message
    
    def fetch_visualization_data(self, query, filters=None):
        """Fetch data for visualizations."""
        # Return an error message for visualization data
        error_message = ("Visualization data from the House Clerk website is currently unavailable. "
                        "This data source is under development.")
        
        return None, error_message
    
    def _parse_amount(self, amount_str):
        """Parse amount from string to float."""
        if not amount_str or amount_str.lower() in ['n/a', 'none', 'not applicable']:
            return None
        
        try:
            # Remove currency symbols and commas
            clean_amount = amount_str.replace('$', '').replace(',', '')
            # Extract numbers using regex
            number_match = re.search(r'[\d.]+', clean_amount)
            if number_match:
                return float(number_match.group(0))
            return None
        except (ValueError, TypeError):
            return None
    
    def _extract_year(self, date_str):
        """Extract year from date string."""
        if not date_str:
            return ""
        
        # Try to find 4-digit year in the string
        year_match = re.search(r'20\d{2}|19\d{2}', date_str)
        if year_match:
            return year_match.group(0)
        
        return ""