#!/bin/bash

# Azure Web App startup script for FastAPI with Uvicorn
# This script is executed by Azure's Oryx build system

set -e

# Install dependencies if requirements.txt exists
if [ -f "backend/requirements.txt" ]; then
    echo "Installing Python dependencies..."
    pip install --upgrade pip
    pip install -r backend/requirements.txt
else
    echo "Warning: backend/requirements.txt not found"
fi

# Change to backend directory and start Uvicorn
cd backend

# Get port from environment variable (Azure sets PORT)
PORT=${PORT:-8000}

echo "Starting Uvicorn on port $PORT..."
exec gunicorn --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT app.main:app
