# Student Accommodation Rent vs Buy Calculator

A comprehensive web application to analyze and compare renting versus buying a student accommodation property, taking into account various financial factors and scenarios.

## Features

- Detailed financial analysis of rent vs buy scenarios
- Consideration of room rental income
- UK-specific stamp duty calculations
- Cash flow analysis and visualization
- Property appreciation and investment return comparisons
- Flexible selling timeline analysis
- Interactive charts and graphs
- Detailed cost breakdowns

## Project Structure

- `frontend/` - React + TypeScript frontend application
- `backend/` - Python FastAPI backend with financial calculations

## Setup Instructions

### Backend Setup
1. Navigate to the backend directory
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Unix/MacOS: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Run the server: `uvicorn main:app --reload`

### Frontend Setup
1. Navigate to the frontend directory
2. Install dependencies: `npm install`
3. Start the development server: `npm start`

## Usage

1. Access the application at `http://localhost:3000`
2. Input your financial parameters
3. View detailed analysis and recommendations
4. Export results if needed

## Technologies Used

- Frontend: React, TypeScript, Chart.js, Material-UI
- Backend: Python, FastAPI, Pandas, NumPy 