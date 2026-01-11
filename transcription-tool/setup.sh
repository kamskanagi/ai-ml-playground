#!/bin/bash

echo "🚀 Setting up AI Transcription Tool..."
echo ""

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama is not installed!"
    echo "Please install Ollama from: https://ollama.ai/download"
    echo ""
    exit 1
fi

echo "✅ Ollama is installed"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed!"
    exit 1
fi

echo "✅ Python 3 is installed"

# Check if Node is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed!"
    exit 1
fi

echo "✅ Node.js is installed"
echo ""

# Pull Ollama model
echo "📥 Pulling Ollama model (this may take a few minutes)..."
ollama pull llama3
echo "✅ Ollama model ready"
echo ""

# Setup backend
echo "🔧 Setting up backend..."
cd backend

if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing Python dependencies (this may take several minutes)..."
pip install --upgrade pip
pip install -r requirements.txt

cd ..
echo "✅ Backend setup complete"
echo ""

# Setup frontend
echo "🔧 Setting up frontend..."
cd frontend

if [ ! -d "node_modules" ]; then
    echo "Installing Node dependencies (this may take a few minutes)..."
    npm install
fi

cd ..
echo "✅ Frontend setup complete"
echo ""

echo "✨ Setup complete!"
echo ""
echo "To start the application, run:"
echo "  ./start.sh"
echo ""
echo "Or manually:"
echo "  Terminal 1: cd backend && source venv/bin/activate && uvicorn app.main:app --reload"
echo "  Terminal 2: cd frontend && npm start"
