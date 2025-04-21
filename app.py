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
from utils.error_handling import api_error_handler, validate_search_params, handle_api_response
from utils.caching import app_cache, cached
from utils.visualization import LobbyingVisualizer

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

# Configure app for longer request processing
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

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
# Initialize data sources as None first
senate_lda = None
house_disclosures = None 
ny_state = None
nyc = None

# Create session for making API requests
session = requests.Session()
session.headers.update({
    'User-Agent': 'LobbyingDisclosureApp/1.0',
    'Accept': 'application/json'
})

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

# For visualization
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

# Use the exact environment variable name from your .env file
LDA_API_KEY = os.getenv("LDA_API_KEY")

# Import data sources
from data_sources.enhanced_senate_lda import ImprovedSenateLDADataSource as EnhancedSenateLDADataSource
from data_sources.house_disclosures import HouseDisclosuresDataSource

# Initialize data sources
senate_lda = EnhancedSenateLDADataSource(LDA_API_KEY)
house_disclosures = HouseDisclosuresDataSource()

@app.route('/')
def index():
    """Render the search form homepage."""
    return render_template('index.html')

@app.route('/search-lobbying', methods=['POST'])
@api_error_handler
def search_lobbying():
    """Process search form submission."""
    # Extract search parameters from form
    name = request.form.get('name', '').strip()
    company = request.form.get('company', '').strip()
    
    # Get advanced search parameters if provided
    year_from = request.form.get('year_from', '').strip()
    year_to = request.form.get('year_to', '').strip()
    issue_area = request.form.get('issue_area', '').strip()
    agency = request.form.get('agency', '').strip()
    amount_min = request.form.get('amount_min', '').strip()
    data_source = request.form.get('data_source', 'senate').strip()
    
    # New parameter for items per page (default to 25)
    items_per_page = request.form.get('items_per_page', '25').strip()
    try:
        items_per_page = int(items_per_page)
        # Set reasonable limits
        if items_per_page < 10:
            items_per_page = 10
        elif items_per_page > 100:
            items_per_page = 100
    except ValueError:
        items_per_page = 25
    
    # Store search parameters in session for pagination
    session['search_name'] = name
    session['search_company'] = company
    session['year_from'] = year_from
    session['year_to'] = year_to
    session['issue_area'] = issue_area
    session['agency'] = agency
    session['amount_min'] = amount_min
    session['data_source'] = data_source
    session['items_per_page'] = items_per_page
    
    return redirect(url_for('show_results', page=1))

@app.route('/results/<int:page>')
@api_error_handler
def show_results(page):
    """Display search results with pagination."""
    # Get search parameters from session
    name = session.get('search_name', '')
    company = session.get('search_company', '')
    year_from = session.get('year_from', '')
    year_to = session.get('year_to', '')
    issue_area = session.get('issue_area', '')
    agency = session.get('agency', '')
    amount_min = session.get('amount_min', '')
    data_source = session.get('data_source', 'senate')
    items_per_page = session.get('items_per_page', 25)
    
    if not name and not company:
        flash("Please enter a name or a company to search.", "error")
        return redirect(url_for('index'))
    
    # Primary search query is name or company
    query = name if name else company
    
    # Create filters dict
    filters = {
        'year_from': year_from,
        'year_to': year_to,
        'issue_area': issue_area,
        'agency': agency,
        'amount_min': amount_min,
        'is_person': bool(name)
    }
    
    # Select the appropriate data source
    if data_source == 'senate':
        data_source_obj = senate_lda
    elif data_source == 'house':
        data_source_obj = house_disclosures
    else:
        flash(f"Data source '{data_source}' is not yet implemented.", "error")
        return redirect(url_for('index'))
    
    # Fetch results from the selected data source
    results, count, pagination, error = data_source_obj.search_filings(
        query, 
        filters=filters,
        page=page,
        page_size=items_per_page  # Use the stored items_per_page value
    )
    
    if error:
        flash(f"Error retrieving results: {error}", "error")
    
    return render_template(
        'results.html',
        name=name,
        company=company,
        results=results,
        count=count,
        pagination=pagination,
        current_page=page,
        query=query,
        error=error,
        data_source=data_source,
        year_from=year_from,
        year_to=year_to,
        issue_area=issue_area,
        agency=agency,
        amount_min=amount_min,
        items_per_page=items_per_page  # Pass to template
    )

@app.route('/filing/<string:filing_id>')
@api_error_handler
def filing_detail(filing_id):
    """Display detailed information for a specific filing."""
    # Get the data source from session
    data_source = session.get('data_source', 'senate')
    
    # Select the appropriate data source
    if data_source == 'senate':
        data_source_obj = senate_lda
    elif data_source == 'house':
        data_source_obj = house_disclosures
    else:
        flash(f"Data source '{data_source}' is not yet implemented.", "error")
        return redirect(url_for('index'))
    
    # Fetch filing details
    filing, error = data_source_obj.get_filing_detail(filing_id)
    
    if error:
        flash(f"Error retrieving filing: {error}", "error")
        return redirect(url_for('index'))
    
    if not filing:
        flash("Filing not found.", "error")
        return redirect(url_for('index'))
        
    return render_template('filing_detail.html', filing=filing, data_source=data_source)

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
    
    # Get visualization data
    visualization_data, error = data_source_obj.fetch_visualization_data(query, filters)
    
    if error or not visualization_data:
        flash(f"Error retrieving data for visualization: {error if error else 'No data found'}", "error")
        return redirect(url_for('index'))
    
    # Prepare data for visualization
    years_data = visualization_data.get("years_data", {})
    registrants_data = visualization_data.get("registrants_data", {})
    amounts_data = visualization_data.get("amounts_data", [])
    
    # Generate visualizations
    charts = visualizer.generate_visualizations(query, results, visualization_data)
    
    # 1. Filings by Year
    if years_data:
        fig, ax = plt.subplots(figsize=(10, 6))
        years = sorted(years_data.keys())
        counts = [years_data[year] for year in years]
        ax.bar(years, counts, color='steelblue')
        ax.set_xlabel('Year')
        ax.set_ylabel('Number of Filings')
        ax.set_title(f'Lobbying Filings by Year for "{query}"')
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        
        # Format x-axis to show all years
        if len(years) > 10:
            plt.xticks(rotation=45)
        
        # Save chart to buffer
        buffer = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        filings_by_year_chart = base64.b64encode(buffer.getvalue()).decode('utf-8')
        plt.close(fig)
        charts.append(('filings_by_year', filings_by_year_chart))
    
    # 2. Top Registrants
    if registrants_data:
        # Get top 10 registrants
        top_registrants = sorted(registrants_data.items(), key=lambda x: x[1], reverse=True)[:10]
        
        if top_registrants:
            fig, ax = plt.subplots(figsize=(10, 6))
            registrant_names = [r[0] if len(r[0]) < 25 else r[0][:22] + '...' for r in top_registrants]
            registrant_counts = [r[1] for r in top_registrants]
            
            # Create horizontal bar chart
            bars = ax.barh(registrant_names, registrant_counts, color='lightseagreen')
            ax.set_xlabel('Number of Filings')
            ax.set_title(f'Top 10 Lobbying Firms for "{query}"')
            ax.grid(axis='x', linestyle='--', alpha=0.7)
            
            # Add count labels to bars
            for bar in bars:
                width = bar.get_width()
                ax.text(width + 0.1, bar.get_y() + bar.get_height()/2, f'{width:.0f}', 
                        ha='left', va='center')
            
            # Save chart to buffer
            buffer = io.BytesIO()
            plt.tight_layout()
            plt.savefig(buffer, format='png')
            buffer.seek(0)
            top_registrants_chart = base64.b64encode(buffer.getvalue()).decode('utf-8')
            plt.close(fig)
            charts.append(('top_registrants', top_registrants_chart))
    
    # 3. Amount Trends Over Time (if we have enough data)
    if len(amounts_data) > 5:
        # Sort by date
        try:
            # Convert dates to datetime objects for sorting
            date_amount_pairs = []
            for date_str, amount in amounts_data:
                try:
                    # Try multiple date formats
                    date_formats = [
                        "%b %d, %Y",  # e.g. "Jan 01, 2020"
                        "%Y-%m-%d",   # e.g. "2020-01-01"
                        "%m/%d/%Y",   # e.g. "01/01/2020"
                    ]
                    
                    date_obj = None
                    for fmt in date_formats:
                        try:
                            date_obj = datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue
                    
                    if date_obj:
                        date_amount_pairs.append((date_obj, amount))
                except:
                    continue
            
            # Sort by date
            date_amount_pairs.sort(key=lambda x: x[0])
            
            if date_amount_pairs:
                # Create the chart
                fig, ax = plt.subplots(figsize=(10, 6))
                dates = [pair[0] for pair in date_amount_pairs]
                amounts = [pair[1] for pair in date_amount_pairs]
                
                ax.plot(dates, amounts, marker='o', linestyle='-', color='teal')
                ax.set_xlabel('Date')
                ax.set_ylabel('Amount (USD)')
                ax.set_title(f'Lobbying Expenditure Trends for "{query}"')
                ax.grid(True, linestyle='--', alpha=0.7)
                
                # Format y-axis as currency
                ax.yaxis.set_major_formatter('${x:,.0f}')
                
                # Rotate date labels for better readability
                plt.xticks(rotation=45)
                
                # Save chart to buffer
                buffer = io.BytesIO()
                plt.tight_layout()
                plt.savefig(buffer, format='png')
                buffer.seek(0)
                amount_trend_chart = base64.b64encode(buffer.getvalue()).decode('utf-8')
                plt.close(fig)
                charts.append(('amount_trend', amount_trend_chart))
        except Exception as e:
            print(f"Error creating amount trend chart: {e}")
    
    # Render the visualization template with the data source name
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

@app.template_filter('truncate_text')
def truncate_text(text, length=150):
    """Truncate text to the specified length."""
    if not text:
        return "N/A"
    if len(text) <= length:
        return text
    return text[:length] + "..."

if __name__ == '__main__':
    app.run(debug=True)