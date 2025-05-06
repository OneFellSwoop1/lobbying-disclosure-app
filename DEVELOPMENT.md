# Multi-Computer Development Guide

This guide outlines how to work on this project across multiple computers.

## Project Structure

The project has the following key components:

- **Data Sources**: Located in `data_sources/` directory - Only the `improved_senate_lda.py` is currently active
- **Templates**: Located in `templates/` directory - HTML templates for the UI
- **Static Files**: Located in `static/` directory - CSS, JavaScript, and images
- **Utility Functions**: Located in `utils/` directory
- **Main Application**: `app.py` - The Flask application that handles routing and logic

## Working Across Multiple Computers

### Initial Setup on Each Computer

```bash
# Clone the repository (do this once per computer)
git clone https://github.com/OneFellSwoop1/lobbying-disclosure-app.git
cd lobbying-disclosure-app

# Set up the development environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create .env file with your API keys
echo "LDA_API_KEY=your_api_key_here" > .env
```

### Daily Workflow

Before starting work each day:

```bash
# Pull the latest changes
git pull origin master

# Activate the virtual environment if not already active
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install any new dependencies
pip install -r requirements.txt
```

After making changes:

```bash
# See what files you have changed
git status

# Add your changes
git add .

# Commit your changes with a descriptive message
git commit -m "Description of your changes"

# Push your changes to GitHub
git push origin master
```
