# data_sources/base.py
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

class LobbyingDataSource(ABC):
    """Base class for all lobbying data sources."""
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the name of this data source."""
        pass
    
    @property
    @abstractmethod
    def government_level(self) -> str:
        """Return the level of government (Federal, State, Local)."""
        pass
    
    def search_filings(self, query, filters=None, page=1, page_size=10):
        """
        Search for lobbying filings with the given parameters.
        
        Args:
            query: The search query (person or entity name)
            filters: Additional filters to apply to the search
            page: Page number for pagination
            page_size: Number of results per page
            
        Returns:
            tuple: (results, count, pagination_info, error)
        """
        raise NotImplementedError("Subclasses must implement this method")
    
    def get_filing_detail(self, filing_id):
        """
        Get detailed information about a specific filing.
        
        Args:
            filing_id: The unique identifier for the filing
            
        Returns:
            tuple: (filing_data, error)
        """
        raise NotImplementedError("Subclasses must implement this method")
    
    def fetch_visualization_data(self, query, filters=None):
        """
        Fetch data specifically for visualization purposes.
        
        Returns:
            tuple: (visualization_data, error)
        """
        raise NotImplementedError("Subclasses must implement this method")