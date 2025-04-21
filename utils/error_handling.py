# utils/error_handling.py
"""
Error handling utilities for the Lobbying Disclosure App.
This module provides consistent error handling and user feedback.
"""

import logging
import traceback
from functools import wraps
from flask import flash, redirect, url_for

logger = logging.getLogger('error_handling')

class ApiError(Exception):
    """Custom exception for API-related errors"""
    def __init__(self, message, status_code=None, details=None):
        self.message = message
        self.status_code = status_code
        self.details = details
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
        except ApiError as e:
            logger.error(f"API Error: {e.message}")
            if e.details:
                logger.error(f"Details: {e.details}")
            
            # Flash user-friendly message
            flash(f"API Error: {e.message}", "error")
            return redirect(url_for('index'))
        except DataSourceError as e:
            logger.error(f"Data Source Error: {e.message}")
            if e.details:
                logger.error(f"Details: {e.details}")
            
            # Flash user-friendly message
            source_name = e.source or "data source"
            flash(f"Error accessing {source_name}: {e.message}", "error")
            return redirect(url_for('index'))
        except ValidationError as e:
            logger.warning(f"Validation Error: {e.message}")
            
            # Flash specific field error if available
            if e.field:
                flash(f"Invalid input for {e.field}: {e.message}", "error")
            else:
                flash(f"Invalid input: {e.message}", "error")
            return redirect(url_for('index'))
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Flash generic error message to user
            flash("An unexpected error occurred. Please try again later.", "error")
            return redirect(url_for('index'))
    return decorated_function

def validate_search_params(name, company, data_source):
    """Validate search parameters and raise ValidationError if invalid"""
    if not name and not company:
        raise ValidationError("Please enter a name or company to search.")
    
    if data_source not in ['senate', 'house', 'ny_state', 'nyc']:
        raise ValidationError("Invalid data source selected.", "data_source")
    
    # Return True if validation passes
    return True

def handle_api_response(results, count, pagination, error):
    """Handle API response and raise appropriate exceptions if needed"""
    if error:
        if "authentication failed" in error.lower() or "api key" in error.lower():
            raise ApiError("Authentication failed. Please check your API key.", 401, error)
        elif "rate limit" in error.lower():
            raise ApiError("Rate limit exceeded. Please try again later.", 429, error)
        elif "no data found" in error.lower() or "not found" in error.lower():
            # This is not really an error, just no results
            return results, count, pagination
        else:
            raise ApiError(f"Error retrieving data: {error}")
    
    return results, count, pagination