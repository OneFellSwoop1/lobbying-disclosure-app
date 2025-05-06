#!/bin/bash

echo "Restarting the Lobbying Disclosure App..."

# Kill any running Flask processes on port 5001
echo "Stopping any existing processes on port 5001..."
lsof -ti:5001 | xargs kill -9 2>/dev/null || echo "No processes found on port 5001"

# Activate virtual environment and start the app
echo "Starting Flask app..."
source venv/bin/activate
python app.py

echo "App started!" 