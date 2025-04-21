# utils/visualization.py
"""
Enhanced visualization utilities for the Lobbying Disclosure App.
This module provides improved chart generation with more insightful visualizations.
"""

import io
import base64
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict

# For visualization
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

logger = logging.getLogger('visualization')

class LobbyingVisualizer:
    """Class to generate visualizations for lobbying data"""
    
    def __init__(self, theme='default'):
        """
        Initialize the visualizer.
        
        Args:
            theme: Visual theme to use ('default', 'dark', 'light', etc.)
        """
        self.theme = theme
        self._setup_plot_style()
    
    def _setup_plot_style(self):
        """Configure plot styling based on theme"""
        if self.theme == 'dark':
            plt.style.use('dark_background')
            self.colors = {
                'primary': '#5e72e4',
                'secondary': '#11cdef',
                'success': '#2dce89',
                'info': '#6772e5',
                'warning': '#fb6340',
                'danger': '#f5365c',
                'light': '#adb5bd',
                'dark': '#212529',
                'text': '#ffffff',
                'background': '#2a2a2a'
            }
        else:  # default or light theme
            plt.style.use('seaborn-v0_8-whitegrid')
            self.colors = {
                'primary': '#5e72e4',
                'secondary': '#11cdef',
                'success': '#2dce89',
                'info': '#6772e5',
                'warning': '#fb6340',
                'danger': '#f5365c',
                'light': '#f8f9fa',
                'dark': '#212529',
                'text': '#212529',
                'background': '#ffffff'
            }
        
        # Configure maptlotlib rcParams for consistent styling
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
        plt.rcParams['figure.figsize'] = (10, 6)
        plt.rcParams['figure.dpi'] = 100
        plt.rcParams['axes.labelsize'] = 12
        plt.rcParams['axes.titlesize'] = 14
        plt.rcParams['axes.titleweight'] = 'bold'
        plt.rcParams['xtick.labelsize'] = 10
        plt.rcParams['ytick.labelsize'] = 10
        plt.rcParams['legend.fontsize'] = 10
    
    def create_filings_by_year_chart(self, years_data):
        """
        Create a chart showing lobbying filings by year.
        
        Args:
            years_data: Dictionary with years as keys and filing counts as values
            
        Returns:
            base64-encoded PNG image
        """
        if not years_data:
            return None
        
        try:
            # Convert data to pandas Series for easier manipulation
            years_series = pd.Series(years_data)
            
            # Sort by year
            years_series = years_series.sort_index()
            
            # Create figure and axis
            fig, ax = plt.subplots(figsize=(10, 6))
            
            # Plot bar chart
            bars = ax.bar(
                years_series.index, 
                years_series.values,
                color=self.colors['primary'],
                width=0.7
            )
            
            # Add data labels on top of bars
            for bar in bars:
                height = bar.get_height()
                ax.text(
                    bar.get_x() + bar.get_width()/2.,
                    height + 0.1,
                    f"{int(height)}",
                    ha='center', 
                    va='bottom',
                    fontweight='bold',
                    color=self.colors['text']
                )
            
            # Customize axes
            ax.set_xlabel('Year', fontweight='bold')
            ax.set_ylabel('Number of Filings', fontweight='bold')
            ax.set_title('Lobbying Filings by Year', fontweight='bold', fontsize=16)
            
            # Adjust x-axis ticks if many years
            if len(years_series) > 8:
                plt.xticks(rotation=45)
            
            # Add grid
            ax.grid(axis='y', linestyle='--', alpha=0.7)
            
            # Add trend line
            if len(years_series) >= 3:
                x_values = np.arange(len(years_series))
                y_values = years_series.values
                z = np.polyfit(x_values, y_values, 1)
                p = np.poly1d(z)
                ax.plot(
                    years_series.index, 
                    p(x_values), 
                    "r--", 
                    color=self.colors['danger'],
                    linewidth=2,
                    label=f"Trend: {'Increasing' if z[0] > 0 else 'Decreasing'}"
                )
                ax.legend()
            
            # Tight layout
            plt.tight_layout()
            
            # Convert to base64 image
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png')
            buffer.seek(0)
            image_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
            plt.close(fig)
            
            return image_data
        
        except Exception as e:
            logger.error(f"Error creating filings by year chart: {str(e)}")
            return None
    
    def create_top_registrants_chart(self, registrants_data, limit=10):
        """
        Create a chart showing top lobbying firms.
        
        Args:
            registrants_data: Dictionary with registrant names as keys and counts as values
            limit: Number of top registrants to show
            
        Returns:
            base64-encoded PNG image
        """
        if not registrants_data:
            return None
        
        try:
            # Convert to pandas Series and get top N
            registrants_series = pd.Series(registrants_data)
            top_registrants = registrants_series.sort_values(ascending=False).head(limit)
            
            # Create figure and axis
            fig, ax = plt.subplots(figsize=(10, 8))  # Taller figure for horizontal bars
            
            # Truncate long registrant names
            top_registrants.index = [name[:30] + '...' if len(name) > 30 else name for name in top_registrants.index]
            
            # Plot horizontal bar chart
            bars = ax.barh(
                top_registrants.index,
                top_registrants.values,
                color=self.colors['info'],
                height=0.7
            )
            
            # Add data labels
            for bar in bars:
                width = bar.get_width()
                ax.text(
                    width + 0.3,
                    bar.get_y() + bar.get_height()/2.,
                    f"{int(width)}",
                    ha='left',
                    va='center',
                    fontweight='bold',
                    color=self.colors['text']
                )
            
            # Customize axes
            ax.set_xlabel('Number of Filings', fontweight='bold')
            ax.set_title('Top Lobbying Firms', fontweight='bold', fontsize=16)
            
            # Add grid
            ax.grid(axis='x', linestyle='--', alpha=0.7)
            
            # Invert y-axis to have highest value at the top
            ax.invert_yaxis()
            
            # Tight layout
            plt.tight_layout()
            
            # Convert to base64 image
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png')
            buffer.seek(0)
            image_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
            plt.close(fig)
            
            return image_data
            
        except Exception as e:
            logger.error(f"Error creating top registrants chart: {str(e)}")
            return None
    
    def create_amount_trend_chart(self, amounts_data):
        """
        Create a chart showing lobbying expenditure trends.
        
        Args:
            amounts_data: List of tuples (date_str, amount)
            
        Returns:
            base64-encoded PNG image
        """
        if not amounts_data or len(amounts_data) < 3:
            return None
        
        try:
            # Convert to pandas DataFrame
            df = pd.DataFrame(amounts_data, columns=['date', 'amount'])
            
            # Parse dates
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            
            # Drop rows with invalid dates
            df = df.dropna(subset=['date'])
            
            # Sort by date
            df = df.sort_values('date')
            
            # Create figure and axis
            fig, ax = plt.subplots(figsize=(10, 6))
            
            # Plot line chart
            ax.plot(
                df['date'],
                df['amount'],
                marker='o',
                linestyle='-',
                color=self.colors['success'],
                markersize=6,
                markerfacecolor=self.colors['background'],
                markeredgecolor=self.colors['success'],
                markeredgewidth=2
            )
            
            # Format y-axis as currency
            formatter = FuncFormatter(lambda x, p: f"${x:,.0f}")
            ax.yaxis.set_major_formatter(formatter)
            
            # Format x-axis dates
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.xticks(rotation=45)
            
            # Customize axes
            ax.set_xlabel('Date', fontweight='bold')
            ax.set_ylabel('Amount (USD)', fontweight='bold')
            ax.set_title('Lobbying Expenditure Trends', fontweight='bold', fontsize=16)
            
            # Add grid
            ax.grid(True, linestyle='--', alpha=0.7)
            
            # Add trend line
            x_values = np.arange(len(df))
            y_values = df['amount'].values
            z = np.polyfit(x_values, y_values, 1)
            p = np.poly1d(z)
            
            ax.plot(
                df['date'],
                p(x_values),
                "r--",
                color=self.colors['warning'],
                linewidth=2,
                label=f"Trend: {'Increasing' if z[0] > 0 else 'Decreasing'}"
            )
            
            # Calculate and display statistics
            total_spent = df['amount'].sum()
            avg_spent = df['amount'].mean()
            max_spent = df['amount'].max()
            max_date = df.loc[df['amount'].idxmax(), 'date'].strftime('%b %Y')
            
            stats_text = (
                f"Total: ${total_spent:,.0f}\n"
                f"Average: ${avg_spent:,.0f}\n"
                f"Peak: ${max_spent:,.0f} ({max_date})"
            )
            
            # Add stats textbox
            props = dict(boxstyle='round', facecolor=self.colors['light'], alpha=0.5)
            ax.text(
                0.05, 0.95, stats_text,
                transform=ax.transAxes,
                fontsize=10,
                verticalalignment='top',
                bbox=props
            )
            
            ax.legend()
            
            # Tight layout
            plt.tight_layout()
            
            # Convert to base64 image
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png')
            buffer.seek(0)
            image_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
            plt.close(fig)
            
            return image_data
            
        except Exception as e:
            logger.error(f"Error creating amount trend chart: {str(e)}")
            return None
    
    def create_issues_pie_chart(self, results):
        """
        Create a pie chart showing distribution of lobbying issues.
        
        Args:
            results: List of filing results to analyze
            
        Returns:
            base64-encoded PNG image
        """
        if not results:
            return None
        
        try:
            # Extract issues from results
            issue_counter = defaultdict(int)
            
            for filing in results:
                issues_text = filing.get('issues', '')
                
                # Look for "Area: X" pattern
                for issue in issues_text.split(';'):
                    issue = issue.strip()
                    if issue.startswith('Area:'):
                        area = issue.replace('Area:', '').strip()
                        issue_counter[area] += 1
            
            # If no structured issues found, return None
            if not issue_counter:
                return None
            
            # Get top 10 issues
            top_issues = dict(sorted(issue_counter.items(), key=lambda x: x[1], reverse=True)[:10])
            
            # Create figure and axis
            fig, ax = plt.subplots(figsize=(10, 8))
            
            # Create pie chart
            wedges, texts, autotexts = ax.pie(
                top_issues.values(),
                labels=None,
                autopct='%1.1f%%',
                startangle=90,
                shadow=False,
                wedgeprops={'edgecolor': 'w'},
                textprops={'fontsize': 12, 'weight': 'bold'}
            )
            
            # Equal aspect ratio ensures that pie is drawn as a circle
            ax.axis('equal')
            
            # Create legend with issue names
            ax.legend(
                wedges,
                top_issues.keys(),
                title="Issue Areas",
                loc="center left",
                bbox_to_anchor=(1, 0, 0.5, 1)
            )
            
            # Set title
            ax.set_title('Distribution of Lobbying Issue Areas', fontweight='bold', fontsize=16)
            
            # Tight layout with extra padding for legend
            plt.tight_layout(rect=[0, 0, 0.85, 1])
            
            # Convert to base64 image
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png')
            buffer.seek(0)
            image_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
            plt.close(fig)
            
            return image_data
            
        except Exception as e:
            logger.error(f"Error creating issues pie chart: {str(e)}")
            return None
    
    def generate_visualizations(self, query, results, visualization_data):
        """
        Generate all visualizations for a query.
        
        Args:
            query: The search query
            results: List of filing results
            visualization_data: Dictionary with visualization data
            
        Returns:
            Dictionary of visualization charts
        """
        charts = {}
        
        # Years data chart
        years_data = visualization_data.get('years_data', {})
        if years_data:
            years_chart = self.create_filings_by_year_chart(years_data)
            if years_chart:
                charts['filings_by_year'] = years_chart
        
        # Top registrants chart
        registrants_data = visualization_data.get('registrants_data', {})
        if registrants_data:
            registrants_chart = self.create_top_registrants_chart(registrants_data)
            if registrants_chart:
                charts['top_registrants'] = registrants_chart
        
        # Amount trend chart
        amounts_data = visualization_data.get('amounts_data', [])
        if amounts_data and len(amounts_data) >= 3:
            amount_chart = self.create_amount_trend_chart(amounts_data)
            if amount_chart:
                charts['amount_trend'] = amount_chart
        
        # Issues pie chart
        if results:
            issues_chart = self.create_issues_pie_chart(results)
            if issues_chart:
                charts['issues_distribution'] = issues_chart
        
        return charts