from pydantic import BaseModel, Field
from typing import Optional


class TranscriptionResponse(BaseModel):
    """Response model for transcription endpoint"""
    success: bool
    transcript: str
    filename: str


class CleanupRequest(BaseModel):
    """Request model for cleanup endpoint"""
    transcript: str = Field(..., min_length=1, description="The transcript to clean up")


class CleanupResponse(BaseModel):
    """Response model for cleanup endpoint"""
    success: bool
    original_transcript: str
    cleaned_transcript: str


class ErrorResponse(BaseModel):
    """Error response model"""
    success: bool = False
    error: str
    detail: Optional[str] = None
