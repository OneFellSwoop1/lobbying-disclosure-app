#!/bin/bash

echo "Cleaning up project directory..."

# Remove Python cache files
echo "Removing Python cache files..."
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} +

# Remove diagnostic files
echo "Removing diagnostic files..."
find . -name "lda_api_diagnostic_*.json" -delete

# Clean cache directory
echo "Cleaning cache directory..."
rm -rf cache/*

# Remove any log backups
echo "Removing log backups..."
find . -name "*.log.*" -delete

echo "Cleanup complete!" 