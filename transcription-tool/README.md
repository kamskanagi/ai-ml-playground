# AI Transcription and Cleanup Tool

A full-stack application that transcribes audio recordings using OpenAI Whisper and cleans up the transcript using a local LLM (Ollama), removing filler words and improving readability.

## Features

- **Audio Transcription**: Convert audio files to text using OpenAI Whisper (local)
- **AI-Powered Cleanup**: Remove filler words and improve transcript readability using Ollama
- **Multiple Modes**:
  - Transcribe & Cleanup (combined)
  - Transcribe Only
  - Cleanup Only (paste your own transcript)
- **Supported Formats**: MP3, WAV, M4A, OGG, FLAC, MP4, WEBM
- **Beautiful UI**: Modern, responsive React interface
- **Easy Deployment**: Docker Compose for one-command setup

## Tech Stack

- **Frontend**: React (JavaScript)
- **Backend**: Python FastAPI
- **Transcription**: OpenAI Whisper (local)
- **LLM**: Ollama (running locally with Llama 3 or Mistral)
- **Deployment**: Docker Compose

## Quick Start (Local - Recommended)

You already have everything installed! Just run:

```bash
./setup.sh    # First time only - installs dependencies
./start.sh    # Starts the application
```

Then open `http://localhost:3000` in your browser!

See [QUICKSTART.md](QUICKSTART.md) for detailed local setup instructions.

## Alternative: Docker Setup

### Prerequisites

- Docker and Docker Compose installed
- At least 8GB RAM (16GB recommended for larger models)
- 10GB free disk space

### 1. Clone or Navigate to the Project

```bash
cd transcription-tool
```

### 2. Start the Services

```bash
docker-compose up -d
```

This will start:
- **Ollama** on port 11434
- **Backend (FastAPI)** on port 8000
- **Frontend (React)** on port 3000

### 3. Pull the LLM Model

After the containers are running, you need to pull an Ollama model:

```bash
# For Llama 3 (recommended)
docker exec -it transcription-ollama ollama pull llama3

# Or for Mistral
docker exec -it transcription-ollama ollama pull mistral

# Or for a smaller/faster model
docker exec -it transcription-ollama ollama pull phi3
```

### 4. Access the Application

Open your browser and navigate to:
```
http://localhost:3000
```

## Usage

### Transcribe & Cleanup Mode (Recommended)
1. Select "Transcribe & Cleanup" mode
2. Upload or drag-and-drop an audio file
3. Click "Transcribe & Cleanup"
4. Wait for processing (this may take a few minutes depending on file length)
5. View both original and cleaned transcripts
6. Copy or download the results

### Transcribe Only Mode
1. Select "Transcribe Only" mode
2. Upload your audio file
3. Click "Transcribe"
4. View and download the raw transcript

### Cleanup Only Mode
1. Select "Cleanup Only" mode
2. Paste an existing transcript in the text area
3. Click "Cleanup Transcript"
4. View and download the cleaned version

## Configuration

### Backend (.env)

Edit `backend/.env` to customize:

```env
# Whisper model size: tiny, base, small, medium, large
WHISPER_MODEL=base

# Ollama configuration
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=llama3
```

**Whisper Model Sizes:**
- `tiny`: Fastest, least accurate (~1GB RAM)
- `base`: Good balance (default) (~1GB RAM)
- `small`: Better accuracy (~2GB RAM)
- `medium`: High accuracy (~5GB RAM)
- `large`: Best accuracy (~10GB RAM)

### Frontend (.env)

Edit `frontend/.env` to customize:

```env
REACT_APP_API_URL=http://localhost:8000
PORT=3000
```

## API Endpoints

### Health Check
```bash
GET http://localhost:8000/health
```

### Transcribe Audio
```bash
POST http://localhost:8000/api/transcribe
Content-Type: multipart/form-data
Body: file (audio file)
```

### Cleanup Transcript
```bash
POST http://localhost:8000/api/cleanup
Content-Type: application/json
Body: {"transcript": "your text here"}
```

### Transcribe and Cleanup (Combined)
```bash
POST http://localhost:8000/api/transcribe-and-cleanup
Content-Type: multipart/form-data
Body: file (audio file)
```

## Development

### Running Locally (Without Docker)

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Make sure Ollama is running locally:
```bash
# Install Ollama from https://ollama.ai
ollama serve
ollama pull llama3
```

#### Frontend

```bash
cd frontend
npm install
npm start
```

## Troubleshooting

### Issue: "Cannot connect to Ollama"
**Solution**: Make sure the Ollama container is running and the model is pulled:
```bash
docker-compose ps
docker exec -it transcription-ollama ollama list
docker exec -it transcription-ollama ollama pull llama3
```

### Issue: "Transcription is slow"
**Solution**:
- Use a smaller Whisper model (e.g., `base` or `tiny`)
- Ensure your audio file isn't too long
- Check system resources (CPU/RAM usage)

### Issue: "Out of memory"
**Solution**:
- Use smaller models (Whisper: `tiny` or `base`, Ollama: `phi3`)
- Increase Docker memory limits
- Process shorter audio files

### Issue: Frontend can't connect to backend
**Solution**:
- Check if backend is running: `curl http://localhost:8000/health`
- Verify CORS settings in backend
- Check browser console for errors

## Project Structure

```
transcription-tool/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── FileUpload.js
│   │   │   └── TranscriptDisplay.js
│   │   ├── services/
│   │   │   └── api.js
│   │   ├── App.js
│   │   ├── App.css
│   │   ├── index.js
│   │   └── index.css
│   ├── public/
│   │   └── index.html
│   ├── package.json
│   ├── Dockerfile
│   └── .env
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI application
│   │   ├── transcription.py # Whisper integration
│   │   ├── cleanup.py       # Ollama integration
│   │   └── models.py        # Pydantic models
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env
├── docker-compose.yml
├── .gitignore
└── README.md
```

## Performance Tips

1. **Use appropriate model sizes**: Start with smaller models and upgrade if needed
2. **Process shorter clips**: For long recordings, consider splitting them
3. **Monitor resources**: Keep an eye on CPU, RAM, and disk usage
4. **Cache models**: Models are cached after first download in Docker volumes

## Available Ollama Models

You can use different models by changing the `OLLAMA_MODEL` in `backend/.env`:

- `llama3` - Meta's Llama 3 (recommended, ~4GB)
- `mistral` - Mistral AI model (~4GB)
- `phi3` - Microsoft's Phi-3 (smaller, ~2GB)
- `gemma` - Google's Gemma (~2GB)

To switch models:
```bash
docker exec -it transcription-ollama ollama pull <model-name>
```

Then update `backend/.env` and restart:
```bash
docker-compose restart backend
```

## License

MIT License - feel free to use this project for personal or commercial purposes.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- [OpenAI Whisper](https://github.com/openai/whisper) for transcription
- [Ollama](https://ollama.ai) for local LLM inference
- [FastAPI](https://fastapi.tiangolo.com/) for the backend framework
- [React](https://react.dev/) for the frontend framework
