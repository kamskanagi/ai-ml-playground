import whisper
import os
import logging

logger = logging.getLogger(__name__)

# Load Whisper model (you can change the model size: tiny, base, small, medium, large)
# For faster transcription, use "base" or "small". For better accuracy, use "medium" or "large"
MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")

# Global variable to cache the model
_model = None


def get_model():
    """
    Get or load the Whisper model (cached for reuse)
    """
    global _model
    if _model is None:
        logger.info(f"Loading Whisper model: {MODEL_SIZE}")
        _model = whisper.load_model(MODEL_SIZE)
        logger.info("Whisper model loaded successfully")
    return _model


def transcribe_audio(audio_path: str) -> str:
    """
    Transcribe audio file using OpenAI Whisper

    Args:
        audio_path: Path to the audio file

    Returns:
        str: Transcribed text

    Raises:
        Exception: If transcription fails
    """
    try:
        logger.info(f"Starting transcription for: {audio_path}")

        # Load the model
        model = get_model()

        # Transcribe the audio
        result = model.transcribe(audio_path)

        # Extract the text
        transcript = result["text"]

        logger.info(f"Transcription completed. Length: {len(transcript)} characters")

        return transcript.strip()

    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        raise Exception(f"Failed to transcribe audio: {str(e)}")
