# Potato Disease Classification

An AI-powered web application that uses deep learning to detect and classify potato leaf diseases with high accuracy.

## Overview

This application helps farmers and agricultural professionals identify common potato diseases by analyzing images of potato leaves. The system can detect:

- **Early Blight**
- **Late Blight**
- **Healthy** leaves

## Features

- 🔍 **Accurate Detection**: Deep learning model trained on potato leaf disease dataset
- ⚡ **Instant Results**: Get predictions in seconds with confidence scores
- 📱 **Easy to Use**: Simple drag-and-drop interface
- 🌐 **Web-Based**: No installation required, accessible from any device
- 📊 **Confidence Scores**: Visual representation of prediction confidence

## Technology Stack

### Backend

- **FastAPI**: Modern Python web framework for building APIs
- **TensorFlow**: Deep learning framework for model inference
- **Python 3.7+**: Core programming language
- **Uvicorn**: ASGI server for running the API

### Frontend

- **React**: JavaScript library for building user interfaces
- **React Hooks**: Modern state management
- **CSS3**: Styling with responsive design
- **Fetch API**: HTTP requests to backend

### Model

- **CNN Architecture**: Convolutional Neural Network
- **TensorFlow/Keras**: Model training and deployment
- **Image Data Generator**: Data augmentation and preprocessing

## Installation

### Prerequisites

- Python 3.7 or higher
- Node.js 14 or higher
- npm or yarn

### Backend Setup

1. Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install Python dependencies:

```bash
cd api
pip install -r requirements.txt
```

3. Ensure the trained model exists at `models/potatoes.h5`

### Frontend Setup

1. Navigate to the frontend directory:

```bash
cd frontend
```

2. Install Node.js dependencies:

```bash
npm install
```

## Running the Application

### Start the Backend Server

```bash
cd api
source ../venv/bin/activate
python main.py
```

The backend API will be available at `http://localhost:8000`

### Start the Frontend Development Server

In a new terminal:

```bash
cd frontend
npm start
```

The React application will open at `http://localhost:3000`

## Usage

1. Open your browser and navigate to `http://localhost:3000`
2. You will see the Potato Disease Classification interface with an introduction section
3. Either:
   - Drag and drop an image of a potato leaf onto the upload area, or
   - Click the upload area to select an image from your device
4. Once uploaded, you'll see a preview of the image
5. Click the **"MAKE PREDICTION"** button to analyze the image
6. View the results showing:
   - Disease classification (Early Blight, Late Blight, or Healthy)
   - Confidence score (as a percentage)
   - Visual confidence bar
7. Click **"RESET"** to analyze another image
