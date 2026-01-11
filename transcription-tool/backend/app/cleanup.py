import requests
import os
import logging
import json

logger = logging.getLogger(__name__)

# Ollama configuration
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")


def cleanup_transcript(transcript: str) -> str:
    """
    Clean up transcript using Ollama LLM

    Args:
        transcript: The raw transcript to clean up

    Returns:
        str: Cleaned up transcript

    Raises:
        Exception: If cleanup fails
    """
    try:
        logger.info(f"Starting cleanup with model: {OLLAMA_MODEL}")

        # Create the prompt for the LLM
        prompt = f"""You are a transcript editor. Clean up the following transcript by:
1. Removing filler words (um, uh, like, you know, etc.)
2. Fixing grammar and punctuation
3. Organizing the text into proper paragraphs
4. Maintaining the original meaning and tone
5. Making it more readable while keeping all important information

Do not add any commentary or explanations. Only return the cleaned transcript.

Original Transcript:
{transcript}

Cleaned Transcript:"""

        # Call Ollama API
        url = f"{OLLAMA_HOST}/api/generate"

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,  # Lower temperature for more consistent output
                "top_p": 0.9,
            }
        }

        logger.info(f"Calling Ollama at {url}")

        response = requests.post(
            url,
            json=payload,
            timeout=300  # 5 minute timeout for longer transcripts
        )

        if response.status_code != 200:
            error_msg = f"Ollama API error: {response.status_code} - {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

        result = response.json()
        cleaned_text = result.get("response", "").strip()

        if not cleaned_text:
            raise Exception("Ollama returned empty response")

        logger.info(f"Cleanup completed. Original length: {len(transcript)}, Cleaned length: {len(cleaned_text)}")

        return cleaned_text

    except requests.exceptions.Timeout:
        error_msg = "Ollama request timed out. The transcript might be too long."
        logger.error(error_msg)
        raise Exception(error_msg)

    except requests.exceptions.ConnectionError:
        error_msg = f"Cannot connect to Ollama at {OLLAMA_HOST}. Make sure Ollama is running."
        logger.error(error_msg)
        raise Exception(error_msg)

    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")
        raise Exception(f"Failed to cleanup transcript: {str(e)}")
