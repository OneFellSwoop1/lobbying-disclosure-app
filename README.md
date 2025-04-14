# Lobbying Disclosure App

A web application that allows users to search and analyze lobbying disclosure data from the Senate's Lobbying Disclosure database.

## Features

- Search for lobbying activities by lobbyist name or organization
- View detailed filing information
- Filter by year, issue area, and agency
- Visualize lobbying data with interactive charts
- Export data to CSV format

## Setup

1. Clone this repository
2. Install the required packages: `pip install -r requirements.txt`
3. Create a `.env` file with your API key:
                           SECRET_KEY=your_secret_key
                            LDA_API_KEY=your_lda_api_key
4. Run the application: `python app.py`

## Technologies Used

- Flask (Python web framework)
- Bootstrap (Frontend)
- Matplotlib (Data visualization)
- Senate LDA API (Data source)
