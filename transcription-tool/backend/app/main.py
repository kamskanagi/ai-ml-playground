from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import tempfile
from pathlib import Path
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from .transcription import transcribe_audio
from .cleanup import cleanup_transcript
from .models import TranscriptionResponse, CleanupRequest, CleanupResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Transcription and Cleanup Tool")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "AI Transcription and Cleanup Tool API"}


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.post("/api/transcribe", response_model=TranscriptionResponse)
async def transcribe(file: UploadFile = File(...)):
    """
    Transcribe an audio file using OpenAI Whisper
    """
    try:
        logger.info(f"Received file: {file.filename}")

        # Validate file type
        allowed_extensions = ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.mp4', '.webm']
        file_ext = Path(file.filename).suffix.lower()

        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format. Allowed formats: {', '.join(allowed_extensions)}"
            )

        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name

        try:
            # Transcribe the audio
            logger.info(f"Transcribing file: {temp_path}")
            transcript = transcribe_audio(temp_path)
            logger.info("Transcription completed successfully")

            return TranscriptionResponse(
                success=True,
                transcript=transcript,
                filename=file.filename
            )

        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    except Exception as e:
        logger.error(f"Error during transcription: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@app.post("/api/cleanup", response_model=CleanupResponse)
async def cleanup(request: CleanupRequest):
    """
    Clean up transcript using local LLM (Ollama)
    """
    try:
        logger.info("Starting transcript cleanup")

        if not request.transcript or len(request.transcript.strip()) == 0:
            raise HTTPException(status_code=400, detail="Transcript cannot be empty")

        # Clean up the transcript
        cleaned_transcript = cleanup_transcript(request.transcript)
        logger.info("Cleanup completed successfully")

        return CleanupResponse(
            success=True,
            original_transcript=request.transcript,
            cleaned_transcript=cleaned_transcript
        )

    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


@app.post("/api/transcribe-and-cleanup", response_model=CleanupResponse)
async def transcribe_and_cleanup(file: UploadFile = File(...)):
    """
    Combined endpoint: Transcribe and clean up in one request
    """
    try:
        # First, transcribe
        transcription_result = await transcribe(file)

        if not transcription_result.success:
            raise HTTPException(status_code=500, detail="Transcription failed")

        # Then, cleanup
        cleanup_request = CleanupRequest(transcript=transcription_result.transcript)
        cleanup_result = await cleanup(cleanup_request)

        return cleanup_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during transcribe-and-cleanup: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Process failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
