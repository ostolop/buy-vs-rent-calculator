#!/bin/bash

# Create backend virtual environment and install dependencies
echo "Setting up backend..."
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start backend server in background
echo "Starting backend server..."
uvicorn main:app --reload &
BACKEND_PID=$!

# Setup frontend
echo "Setting up frontend..."
cd ../frontend
npm install

# Start frontend development server
echo "Starting frontend development server..."
npm start

# Cleanup on exit
trap "kill $BACKEND_PID" EXIT 