from flask import Flask, render_template, request, jsonify, url_for, redirect, flash, session, make_response
import os
from dotenv import load_dotenv
from datetime import datetime
import json
import urllib.parse
import re
import io
import base64
from collections import defaultdict, Counter
import pandas as pd
import numpy as np
import logging
from logging.handlers import RotatingFileHandler
import time
import traceback
import requests
from utils.error_handling import api_error_handler, validate_search_params, handle_api_response, diagnose_api_issue
from utils.caching import app_cache, cached
from utils.visualization import LobbyingVisualizer
from flask_wtf.csrf import CSRFProtect
from data_sources.improved_senate_lda import ImprovedSenateLDADataSource

# For visualization
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt

# Load environment variables from .env file
load_dotenv()

# Setup logging
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Configure logger
logger = logging.getLogger('lobbying_app')
logger.setLevel(logging.INFO)

# Create handlers
file_handler = RotatingFileHandler(
    os.path.join(log_dir, 'app.log'),
    maxBytes=10485760,  # 10MB
    backupCount=10
)
console_handler = logging.StreamHandler()

# Create formatters
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add handlers
logger.addHandler(file_handler)
logger.addHandler(console_handler)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

# Add CSRF protection
csrf = CSRFProtect(app)

# Configure app for longer request processing and security
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size
app.config['WTF_CSRF_ENABLED'] = False  # Temporarily disable CSRF for testing
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable caching for development
app.config['TEMPLATES_AUTO_RELOAD'] = True  # Auto reload templates

# Use the exact environment variable name from your .env file
LDA_API_KEY = os.getenv("LDA_API_KEY")
if not LDA_API_KEY:
    logger.warning("LDA_API_KEY not found in environment variables. API functionality may be limited.")
else:
    logger.info(f"LDA_API_KEY found: {LDA_API_KEY[:5]}...")

# Initialize visualization tools  
visualizer = LobbyingVisualizer()

# Initialize cache directory
cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
os.makedirs(cache_dir, exist_ok=True)

# Initialize data sources
try:
    # Always try real API data first
    senate_lda = ImprovedSenateLDADataSource(LDA_API_KEY, use_mock_data=False)
    logger.info("Successfully initialized Senate LDA data source with real API data")
    
    # Verify API key is working by making a simple API request
    test_result = senate_lda.session.get(f"{senate_lda.api_base_url}/filings/?limit=1", timeout=5)
    if test_result.status_code == 200:
        logger.info("API connection verified successful")
    else:
        logger.warning(f"API connection test returned status code: {test_result.status_code}")
        logger.warning("API key may not be valid, falling back to mock data")
        senate_lda = ImprovedSenateLDADataSource(LDA_API_KEY, use_mock_data=True)
        logger.info("Using mock data as fallback")
except Exception as e:
    logger.error(f"Failed to initialize Senate LDA data source: {str(e)}")
    logger.error(traceback.format_exc())
    # Fall back to mock data if API initialization fails
    try:
        senate_lda = ImprovedSenateLDADataSource(LDA_API_KEY, use_mock_data=True)
        logger.info("Falling back to mock data due to API initialization failure")
    except Exception as e2:
        logger.critical(f"Failed to initialize mock data source: {str(e2)}")
        senate_lda = None

# Set response headers to prevent caching
@app.after_request
def add_header(response):
    """Add headers to prevent caching."""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/')
def index():
    """Render the search form homepage."""
    return render_template('index.html')

@app.route('/search', methods=['GET'])
@api_error_handler
def search():
    """Process search query from get parameters."""
    # Extract search parameters from query string
    query = request.args.get('query', '').strip()
    search_type = request.args.get('search_type', 'registrant').strip().lower()
    filing_type = request.args.get('filing_type', 'all').strip()
    filing_year = request.args.get('filing_year', 'all').strip()
    page = request.args.get('page', '1').strip()
    
    # Convert page to integer, default to 1
    try:
        page = int(page)
        if page < 1:
            page = 1
    except ValueError:
        page = 1
    
    if not query:
        flash("Please enter a search term.", "error")
        return redirect(url_for('index'))
    
    try:
        # Store the search parameters in session
        session['search_query'] = query
        session['search_type'] = search_type
        session['filing_type'] = filing_type
        
        # Handle "All Years" option
        if filing_year and filing_year.lower() != 'all':
            session['filing_year'] = int(filing_year)
        else:
            # If "All Years" is selected, default to current year based on diagnostics findings
            current_year = datetime.now().year
            session['filing_year'] = current_year
            filing_year = str(current_year)
        
        # Log the search attempt with enhanced detail
        logger.info(f"Search request: query='{query}', search_type={search_type}, filing_type={filing_type}, filing_year={filing_year}, page={page}")
            
        # Redirect to results page with query parameters in URL
        return redirect(url_for('show_results', 
                               page=page, 
                               query=query, 
                               search_type=search_type,
                               filing_type=filing_type, 
                               filing_year=filing_year))
        
    except Exception as e:
        logger.error(f"Error in search: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"An error occurred while processing your search: {str(e)}", "error")
        return redirect(url_for('index'))

# Preprocess search query for better matching
def preprocess_search_query(query):
    """Process search query to improve matching."""
    # Convert to lowercase for case-insensitive matching
    processed_query = query.lower()
    
    # Remove special characters but keep spaces
    processed_query = re.sub(r'[^\w\s]', '', processed_query)
    
    # Handle common abbreviations and alternate names based on diagnostic findings
    abbreviation_map = {
        "alphabet": "google",
        "meta": "facebook",
        "msft": "microsoft",
        "ms": "microsoft",
        "amzn": "amazon",
        "goog": "google",
        "googl": "google",
        "fb": "facebook",
        "aapl": "apple",
        "t": "at&t",
        "at&t": "att",
        "att": "at&t",
        "ibm": "international business machines",
        "intl": "international",
        "intl.": "international",
        "svb": "silicon valley bank",
        "jpm": "jpmorgan",
        "jpmorgan": "jpmorgan chase",
        "bofa": "bank of america",
        "gs": "goldman sachs",
        "alphabet inc": "google"
    }
    
    if processed_query in abbreviation_map:
        processed_query = abbreviation_map[processed_query]
    
    # Remove common business suffixes for better matching
    suffixes = [" inc", " incorporated", " corp", " corporation", 
                " llc", " limited", " ltd", " company", " co"]
    for suffix in suffixes:
        if processed_query.endswith(suffix):
            processed_query = processed_query[:-len(suffix)].strip()
            break
    
    logger.info(f"Preprocessed search query: '{query}' → '{processed_query}'")
    return processed_query

# Helper function to generate alternative search terms
def generate_alternative_terms(query):
    """Generate alternative search terms for when no results are found."""
    alt_terms = []
    
    # Remove special characters
    clean_query = re.sub(r'[^\w\s]', '', query)
    if clean_query != query:
        alt_terms.append(clean_query)
    
    # Try variations with and without suffixes
    company_suffixes = [" Inc", " Inc.", " Corp", " Corp.", " LLC", " Company", " Co", " Co.", " Ltd", " Ltd."]
    
    # If query already has a suffix, try without it
    has_suffix = False
    for suffix in company_suffixes:
        if query.endswith(suffix):
            alt_terms.append(query[:-len(suffix)].strip())
            has_suffix = True
            break
    
    # If query doesn't have a suffix, try adding common ones
    if not has_suffix:
        for suffix in [" Inc", " Corp", " LLC"]:
            alt_terms.append(f"{query}{suffix}")
    
    # Try with and without 'The' prefix
    if query.lower().startswith('the '):
        alt_terms.append(query[4:])
    else:
        alt_terms.append(f"The {query}")
    
    # Try handling common abbreviations and alternate names
    abbrev_map = {
        "msft": "Microsoft",
        "ms": "Microsoft",
        "amzn": "Amazon",
        "goog": "Google",
        "googl": "Google",
        "fb": "Facebook",
        "meta": "Facebook",
        "aapl": "Apple",
        "t": "AT&T",
        "at&t": "ATT",
        "att": "AT&T",
        "ibm": "International Business Machines",
        "intl": "International",
        "intl.": "International",
        "svb": "Silicon Valley Bank",
        "jpm": "JPMorgan",
        "jpmorgan": "JPMorgan Chase",
        "bofa": "Bank of America",
        "gs": "Goldman Sachs",
        "alphabet": "Google",
        "alphabet inc": "Google",
    }
    
    # Check for abbreviations
    lower_query = query.lower()
    if lower_query in abbrev_map:
        alt_terms.append(abbrev_map[lower_query])
    
    # Try words in the query separately for multi-word queries
    words = query.split()
    if len(words) > 1:
        # Add individual words as search terms
        for word in words:
            if len(word) > 3:  # Only use meaningful words
                alt_terms.append(word)
        
        # Try first word which is often the company name
        if len(words[0]) > 3:
            alt_terms.append(words[0])
    
    # Remove duplicates and the original query from alternatives
    alt_terms = list(set(alt_terms))
    if query in alt_terms:
        alt_terms.remove(query)
    
    # Sort by length (shortest first) as they're often more general
    alt_terms.sort(key=len)
    
    return alt_terms

@app.route('/search-lobbying', methods=['POST'])
@api_error_handler
def search_lobbying():
    """Process advanced search form submission."""
    # Extract form data
    registrant = request.form.get('registrant', '').strip()
    client = request.form.get('client', '').strip()
    lobbyist = request.form.get('lobbyist', '').strip()
    year_from = request.form.get('year_from', '').strip()
    year_to = request.form.get('year_to', '').strip()
    issue_area = request.form.get('issue_area', '').strip()
    filing_type = request.form.get('filing_type', 'all').strip()
    government_entity = request.form.get('government_entity', '').strip()
    amount_min = request.form.get('amount_min', '').strip()
    data_source = request.form.get('data_source', 'senate').strip()
    items_per_page = request.form.get('items_per_page', '25').strip()
    
    # Validate inputs - at least one search parameter must be provided
    if not registrant and not client and not lobbyist:
        flash("Please enter at least one search term (registrant, client, or lobbyist name).", "error")
        return redirect(url_for('index'))
    
    # Determine primary search term for the URL
    if registrant:
        primary_search = registrant
        search_type = 'registrant'
    elif client:
        primary_search = client
        search_type = 'client'
    elif lobbyist:
        primary_search = lobbyist
        search_type = 'lobbyist'
    
    # Store search parameters in session
    session['search_registrant'] = registrant
    session['search_client'] = client
    session['search_lobbyist'] = lobbyist
    session['year_from'] = year_from
    session['year_to'] = year_to
    session['issue_area'] = issue_area
    session['filing_type'] = filing_type
    session['government_entity'] = government_entity
    session['amount_min'] = amount_min
    session['data_source'] = data_source
    session['items_per_page'] = items_per_page
    session['search_type'] = search_type
    
    # Log the search parameters
    logger.info(f"Advanced search: registrant='{registrant}', client='{client}', lobbyist='{lobbyist}', "
                f"filing_type='{filing_type}', year_from='{year_from}', year_to='{year_to}', "
                f"issue_area='{issue_area}', government_entity='{government_entity}', amount_min='{amount_min}'")
    
    # Redirect to the results page with parameters in URL
    return redirect(url_for('show_results', 
                        page=1, 
                        query=primary_search, 
                        search_type=search_type,
                        filing_type=filing_type, 
                        filing_year=year_from if year_from else '2024'))

@app.route('/results/<int:page>')
@api_error_handler
def show_results(page):
    """Display search results."""
    query = request.args.get('query', '').strip()
    search_type = request.args.get('search_type', 'registrant').strip().lower()
    filing_type = request.args.get('filing_type', 'all').strip()
    filing_year = request.args.get('filing_year', 'all').strip()
    
    if not query:
        flash("Please enter a search term.", "error")
        return redirect(url_for('index'))
    
    # Set reasonable defaults and limits
    if page < 1:
        page = 1
    
    items_per_page = int(session.get('items_per_page', 25))
    
    try:
        # Log the search parameters
        logger.info(f"Showing results for '{query}' with search_type='{search_type}', filters {{'filing_year': {filing_year}, 'filing_type': '{filing_type}'}}, page {page}")
        
        # Prepare search filters
        filters = {
            'search_type': search_type
        }
        
        # Add standard filters
        if filing_type and filing_type.lower() != 'all':
            filters['filing_type'] = filing_type
        
        # Based on diagnostics, filing_year should always be included for better results
        if filing_year and filing_year.lower() != 'all':
            try:
                filters['filing_year'] = int(filing_year)
            except (ValueError, TypeError):
                # Default to current year if invalid
                filters['filing_year'] = datetime.now().year
        else:
            # Default to current year as this gives better results according to diagnostics
            filters['filing_year'] = datetime.now().year
        
        # Add advanced search filters from session
        if session.get('year_from'):
            filters['year_from'] = session.get('year_from')
        if session.get('year_to'):
            filters['year_to'] = session.get('year_to')
        if session.get('issue_area'):
            filters['issue_area'] = session.get('issue_area')
        if session.get('government_entity'):
            filters['government_entity'] = session.get('government_entity')
        if session.get('amount_min'):
            filters['amount_min'] = session.get('amount_min')
        
        # Add secondary search parameters if we're coming from advanced search
        if session.get('search_registrant') and search_type != 'registrant':
            filters['registrant_name'] = session.get('search_registrant')
        if session.get('search_client') and search_type != 'client':
            filters['client_name'] = session.get('search_client')
        if session.get('search_lobbyist') and search_type != 'lobbyist':
            filters['lobbyist_name'] = session.get('search_lobbyist')
                
        # Process the query for better results
        processed_query = preprocess_search_query(query)
        
        # Try to fetch results from the Senate LDA API
        start_time = time.time()
        results, total_count, pagination, error = senate_lda.search_filings(processed_query, filters, page, items_per_page)
        query_time = time.time() - start_time
        
        # Log query timing
        logger.info(f"Query executed in {query_time:.2f} seconds")
        
        # If no results found or error, try secondary search methods based on diagnostics findings
        if (error or not results) and not senate_lda.use_mock_data:
            logger.warning(f"Primary search method failed or found no results: {error if error else 'No results found'}")
            
            # Try alternate search methods - based on diagnostic findings
            alt_search_type = None
            if search_type == 'registrant':
                alt_search_type = 'client'
                logger.info(f"Trying alternate search type: {alt_search_type}")
            elif search_type == 'client':
                alt_search_type = 'registrant'
                logger.info(f"Trying alternate search type: {alt_search_type}")
            
            if alt_search_type:
                # Create a new filters dict with alternate search type
                alt_filters = filters.copy()
                alt_filters['search_type'] = alt_search_type
                
                # Try the alternate search
                logger.info(f"Trying alternate search method with {alt_search_type} for '{processed_query}'")
                alt_results, alt_total_count, alt_pagination, alt_error = senate_lda.search_filings(
                    processed_query, alt_filters, page, items_per_page
                )
                
                # If alternate search worked, use its results
                if not alt_error and alt_results:
                    logger.info(f"Alternate search successful: found {alt_total_count} results with {alt_search_type}")
                    results = alt_results
                    total_count = alt_total_count
                    pagination = alt_pagination
                    error = None
                    flash(f"No results found for '{query}' as {search_type}. Showing results as {alt_search_type} instead.", "info")
            
            # If we still have an error or no results, try with a filing year filter
            if (error or not results) and 'filing_year' not in filters:
                current_year = datetime.now().year
                year_filters = filters.copy()
                year_filters['filing_year'] = current_year
                
                logger.info(f"Trying search with filing year {current_year} for '{processed_query}'")
                year_results, year_total_count, year_pagination, year_error = senate_lda.search_filings(
                    processed_query, year_filters, page, items_per_page
                )
                
                # If this search worked, use its results
                if not year_error and year_results:
                    logger.info(f"Year-filtered search successful: found {year_total_count} results")
                    results = year_results
                    total_count = year_total_count
                    pagination = year_pagination
                    error = None
                    flash(f"Showing results from {current_year} for '{query}'.", "info")
        
        # Try to handle API errors gracefully
        if error or not results:
            logger.warning(f"All search methods failed or found no results: {error if error else 'No results found'}")
            
            # If we got an API error and aren't already using mock data, try with mock data
            if error and not senate_lda.use_mock_data:
                logger.info(f"Falling back to mock data due to API error: {error}")
                
                # Create a mock data client
                mock_client = ImprovedSenateLDADataSource(LDA_API_KEY, use_mock_data=True)
                results, total_count, pagination, _ = mock_client.search_filings(
                    processed_query, filters, page, items_per_page
                )
                
                # Add a warning flash message about using mock data
                flash("The Senate LDA API is currently experiencing issues. Showing generated demo data instead.", "warning")
            elif not results:
                # If no results were found, generate alternative search terms
                alt_terms = generate_alternative_terms(query)
                
                return render_template('results.html', 
                    query=query, 
                    search_type=search_type,
                    results=[], 
                    total_count=0, 
                    page=page, 
                    pagination=None,
                    filters=filters,
                    alt_terms=alt_terms[:5],
                    filing_years=get_available_years()
                )
        
        # Calculate some statistics for the result page
        unique_clients = len(set(f["client"]["name"] for f in results if f.get("client", {}).get("name")))
        
        # Calculate total amount reported
        total_amount = 0
        for filing in results:
            if filing.get("income"):
                try:
                    total_amount += float(filing["income"])
                except (ValueError, TypeError):
                    pass
            elif filing.get("expenses"):
                try:
                    total_amount += float(filing["expenses"])
                except (ValueError, TypeError):
                    pass
        
        # Get latest filing date
        latest_date = None
        for filing in results:
            if filing.get("dt_posted"):
                try:
                    filing_date = datetime.strptime(filing["dt_posted"], "%Y-%m-%d")
                    if latest_date is None or filing_date > latest_date:
                        latest_date = filing_date
                except (ValueError, TypeError):
                    pass
        
        latest_filing_date = latest_date.strftime("%B %d, %Y") if latest_date else "N/A"
        
        # Display a warning if all results are mock data
        all_mock = all(filing.get("meta", {}).get("is_mock", False) for filing in results) if results else False
        if all_mock:
            flash("Showing demonstration data because the Senate LDA API did not return results for your search.", "warning")
        
        # Get a list of available years for filtering
        filing_years = get_available_years()
        
        # Group results by entity if searching for organizations
        if search_type in ['registrant', 'client']:
            # For organization-focused searches, group results by the entity
            grouped_results = {}
            entity_key = 'registrant' if search_type == 'registrant' else 'client'
            
            for filing in results:
                entity = filing.get(entity_key, {})
                entity_id = entity.get('id', 'unknown')
                
                if entity_id not in grouped_results:
                    grouped_results[entity_id] = {
                        'entity': entity,
                        'filings': [],
                        'total_amount': 0,
                        'years': set(),
                        'latest_filing': None
                    }
                
                # Add filing to the group
                grouped_results[entity_id]['filings'].append(filing)
                
                # Update statistics
                amount = 0
                if filing.get("income"):
                    try:
                        amount = float(filing["income"])
                    except (ValueError, TypeError):
                        pass
                elif filing.get("expenses"):
                    try:
                        amount = float(filing["expenses"])
                    except (ValueError, TypeError):
                        pass
                
                grouped_results[entity_id]['total_amount'] += amount
                
                # Track years
                if filing.get('filing_year'):
                    grouped_results[entity_id]['years'].add(filing.get('filing_year'))
                
                # Track latest filing
                if filing.get("dt_posted"):
                    try:
                        filing_date = datetime.strptime(filing["dt_posted"], "%Y-%m-%d")
                        current_latest = grouped_results[entity_id]['latest_filing']
                        
                        if current_latest is None or filing_date > current_latest:
                            grouped_results[entity_id]['latest_filing'] = filing_date
                    except (ValueError, TypeError):
                        pass
            
            # Convert years to sorted list and format latest filing date
            for entity_id, data in grouped_results.items():
                data['years'] = sorted(list(data['years']), reverse=True)
                if data['latest_filing']:
                    data['latest_filing'] = data['latest_filing'].strftime("%B %d, %Y")
                else:
                    data['latest_filing'] = "N/A"
            
            # Convert to list and sort by total amount
            grouped_results_list = list(grouped_results.values())
            grouped_results_list.sort(key=lambda x: x['total_amount'], reverse=True)
            
            return render_template('results.html', 
                query=query,
                search_type=search_type,
                results=results,
                grouped_results=grouped_results_list,
                total_count=total_count, 
                page=page, 
                pagination=pagination,
                filters=filters,
                unique_clients=unique_clients,
                total_amount=int(total_amount),
                latest_filing_date=latest_filing_date,
                filing_years=filing_years,
                current_filing_year=filing_year,
                is_grouped_view=True,
                search_params=session
            )
        else:
            # For lobbyist searches or other types, use the standard view
            return render_template('results.html', 
                query=query,
                search_type=search_type,
                results=results, 
                total_count=total_count, 
                page=page, 
                pagination=pagination,
                filters=filters,
                unique_clients=unique_clients,
                total_amount=int(total_amount),
                latest_filing_date=latest_filing_date,
                filing_years=filing_years,
                current_filing_year=filing_year,
                is_grouped_view=False,
                search_params=session
            )
        
    except Exception as e:
        logger.error(f"Error in search results: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"An error occurred while retrieving search results. Please try again or refine your search terms.", "error")
        return redirect(url_for('index'))

# Helper function to get available years for filtering
def get_available_years():
    current_year = datetime.now().year
    return [str(year) for year in range(current_year, current_year - 6, -1)]

@app.route('/filing/<string:filing_id>')
@api_error_handler
def filing_detail(filing_id):
    """Display detailed information for a specific filing."""
    if not senate_lda:
        flash("Senate LDA API is not available. Please check your API key configuration.", "error")
        return redirect(url_for('index'))
    
    try:
        # Fetch filing details
        filing, error = senate_lda.get_filing_detail(filing_id)
        
        if error:
            logger.error(f"Error retrieving filing: {error}")
            flash(f"Error retrieving filing: {error}", "error")
            return redirect(url_for('index'))
        
        if not filing:
            logger.error(f"Filing not found: {filing_id}")
            flash("Filing not found.", "error")
            return redirect(url_for('index'))
        
        # Process and normalize the filing data for display
        processed_filing = {
            'id': filing.get('id', filing_id),
            'filing_uuid': filing.get('filing_uuid', filing_id),
            'filing_year': filing.get('filing_year', 'N/A'),
            'filing_type_display': filing.get('filing_type_display', 'Unknown'),
            'filing_period': filing.get('period_display', filing.get('filing_period', 'N/A')),
            'dt_posted': filing.get('dt_posted', filing.get('posted_date', 'N/A')),
            'client': filing.get('client', {}),
            'registrant': filing.get('registrant', {}),
            'income': filing.get('income', None),
            'expenses': filing.get('expenses', None),
            'amount': filing.get('amount', None),
            'amount_reported': filing.get('amount_reported', None),
            'lobbying_activities': filing.get('lobbying_activities', []),
            'document_url': filing.get('document_url', None)
        }
        
        return render_template('filing_detail.html', filing=processed_filing)
    except Exception as e:
        logger.error(f"Exception in filing_detail: {str(e)}")
        flash(f"An error occurred while retrieving the filing details: {str(e)}", "error")
        return redirect(url_for('index'))

@app.route('/visualize/<string:query>')
@api_error_handler
def visualize_data(query):
    """Visualize lobbying data for a specific query."""
    # Get search parameters from session
    year_from = session.get('year_from', '')
    year_to = session.get('year_to', '')
    issue_area = session.get('issue_area', '')
    agency = session.get('agency', '')
    amount_min = session.get('amount_min', '')
    data_source = session.get('data_source', 'senate')
    
    # Create filters dict
    filters = {
        'year_from': year_from,
        'year_to': year_to,
        'issue_area': issue_area,
        'agency': agency,
        'amount_min': amount_min,
        'is_person': session.get('search_name', '') != ''
    }
    
    # Select the appropriate data source
    if data_source == 'senate':
        data_source_obj = senate_lda
    elif data_source == 'house':
        data_source_obj = house_disclosures
    else:
        flash(f"Data source '{data_source}' is not yet implemented.", "error")
        return redirect(url_for('index'))
    
    # Get visualization data FIRST
    visualization_data, error = data_source_obj.fetch_visualization_data(query, filters)
    
    if error or not visualization_data:
        flash(f"Error retrieving data for visualization: {error if error else 'No data found'}", "error")
        return redirect(url_for('index'))
    
    # Get search results SECOND
    results, _, _, _ = data_source_obj.search_filings(
        query, 
        filters=filters,
        page=1, 
        page_size=100  # Get a reasonable sample for visualization
    )
    
    # Generate visualizations THIRD
    charts = visualizer.generate_visualizations(query, results, visualization_data)
    
    # Render the template FOURTH
    return render_template(
        'visualize.html',
        query=query,
        count=len(visualization_data.get("years_data", {})),
        charts=charts,
        data_source=data_source
    )

@app.route('/export/<string:query>')
@app.route('/export/<string:query>/<int:limit>')
@api_error_handler
def export_data(query, limit=None):
    """Export lobbying data as CSV."""
    # Get search parameters from session
    year_from = session.get('year_from', '')
    year_to = session.get('year_to', '')
    issue_area = session.get('issue_area', '')
    agency = session.get('agency', '')
    amount_min = session.get('amount_min', '')
    data_source = session.get('data_source', 'senate')
    
    # Create filters dict
    filters = {
        'year_from': year_from,
        'year_to': year_to,
        'issue_area': issue_area,
        'agency': agency,
        'amount_min': amount_min,
        'is_person': session.get('search_name', '') != ''
    }
    
    # Select the appropriate data source
    if data_source == 'senate':
        data_source_obj = senate_lda
    elif data_source == 'house':
        data_source_obj = house_disclosures
    else:
        flash(f"Data source '{data_source}' is not yet implemented.", "error")
        return redirect(url_for('index'))
    
    # Determine export size - default to 250 if not specified
    if limit is None:
        export_size = 250
    else:
        export_size = min(1000, limit)  # Cap at 1000 to prevent server overload
    
    # Fetch results for export
    results, count, _, error = data_source_obj.search_filings(
        query, 
        filters=filters,
        page=1, 
        page_size=export_size
    )
    
    if error or not results:
        flash(f"Error retrieving data for export: {error if error else 'No data found'}", "error")
        return redirect(url_for('index'))
    
    # Convert results to DataFrame
    df = pd.DataFrame(results)
    
    # Prepare CSV data
    csv_data = df.to_csv(index=False)
    
    # Create response with CSV file
    response = make_response(csv_data)
    response.headers["Content-Disposition"] = f"attachment; filename={query}_lobbying_data_{data_source}.csv"
    response.headers["Content-Type"] = "text/csv"
    
    return response

@app.route('/api-diagnostics/<string:query>')
@api_error_handler
def api_diagnostics(query):
    """Diagnostic route to test API connectivity and search parameters."""
    # Only allow in development mode
    if not app.debug:
        flash("API diagnostics are only available in development mode.", "error")
        return redirect(url_for('index'))
    
    if not query:
        flash("Please provide a search query.", "error")
        return redirect(url_for('index'))
    
    search_type = request.args.get('search_type', 'registrant').strip().lower()
    filing_year = request.args.get('filing_year', str(datetime.now().year)).strip()
    
    try:
        # Create filters dict
        filters = {
            'search_type': search_type,
        }
        
        # Add filing_year to filters if provided
        if filing_year.lower() != 'all':
            try:
                filters['filing_year'] = int(filing_year)
            except (ValueError, TypeError):
                filters['filing_year'] = datetime.now().year
        
        # Get API key from the environment
        api_key = os.getenv("LDA_API_KEY")
        if not api_key:
            flash("API key not found in environment variables.", "error")
            return redirect(url_for('index'))
        
        # Run diagnostics
        diagnostic_results = diagnose_api_issue(query, search_type, filters, api_key)
        
        # Save the diagnostic report to a file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        diagnostic_file = f"lda_api_diagnostic_{timestamp}.json"
        
        with open(diagnostic_file, 'w') as f:
            json.dump(diagnostic_results, f, indent=2)
        
        # Show a summary of the results
        successful_tests = [test for test in diagnostic_results['tests'] if test['result'] == 'success']
        failed_tests = [test for test in diagnostic_results['tests'] if test['result'] in ('error', 'exception')]
        no_results_tests = [test for test in diagnostic_results['tests'] if test['result'] == 'no_results']
        
        summary = {
            'query': query,
            'search_type': search_type,
            'filing_year': filters.get('filing_year', 'all'),
            'total_tests': len(diagnostic_results['tests']),
            'successful_tests': len(successful_tests),
            'failed_tests': len(failed_tests),
            'no_results_tests': len(no_results_tests),
            'suggestions': diagnostic_results['suggestions'],
            'diagnostic_file': diagnostic_file
        }
        
        return render_template('api_diagnostics.html', summary=summary, results=diagnostic_results)
    
    except Exception as e:
        logger.error(f"Error in API diagnostics: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"An error occurred during API diagnostics: {str(e)}", "error")
        return redirect(url_for('index'))

@app.template_filter('format_currency')
def format_currency(value):
    """Format a value as currency."""
    if not value:
        return "Not Reported"
    try:
        amount = float(value)
        return f"${amount:,.2f}"
    except (ValueError, TypeError):
        return str(value)

@app.template_filter('format_date')
def format_date(value):
    """Format a date string."""
    if not value:
        return "N/A"
    try:
        # Try to parse the date string
        date_obj = datetime.strptime(value, "%Y-%m-%d")
        return date_obj.strftime("%B %d, %Y")
    except (ValueError, TypeError):
        # If parsing fails, return the original value
        return str(value)

@app.template_filter('truncate_text')
def truncate_text(text, length=150):
    """Truncate text to the specified length."""
    if not text:
        return "N/A"
    if len(text) <= length:
        return text
    return text[:length] + "..."

if __name__ == '__main__':
    app.run(debug=True, port=5001)