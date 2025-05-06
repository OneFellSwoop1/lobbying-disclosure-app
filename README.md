# Lobbying Disclosure App

A web application for searching and analyzing lobbying disclosure data from various government sources.

## Setup

1. Clone the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Create a `.env` file with your API keys:
   ```
   LDA_API_KEY=your_api_key_here
   ```
6. Run the application: `python app.py`
7. Access the application at http://localhost:5001

## Features

- Search Senate LDA filings by registrant, client, or lobbyist name
- View detailed filing information
- Filter results by date, filing type, and other criteria
- Export results to CSV
- Visualize lobbying trends

## Technologies Used

- Flask (Python web framework)
- Bootstrap (Frontend)
- Matplotlib (Data visualization)
- Senate LDA API (Data source)

## Multi-Computer Development Workflow

To work on this project across multiple computers, follow the instructions in [DEVELOPMENT.md](DEVELOPMENT.md).
