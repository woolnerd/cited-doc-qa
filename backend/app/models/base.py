"""Base Pydantic models for API requests and responses."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BaseResponse(BaseModel):
    """Base response model with common fields."""

    success: bool = True
    message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    """Error response model."""

    success: bool = False
    error: str
    detail: str | None = None
    status_code: int

    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str
    environment: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(from_attributes=True)


class DocumentMetadata(BaseModel):
    """Document metadata model."""

    id: UUID
    filename: str
    file_type: str
    upload_date: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class ChunkMetadata(BaseModel):
    """Chunk metadata model."""

    id: UUID
    document_id: UUID
    content: str
    chunk_index: int
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class DocumentUploadResponse(BaseResponse):
    """Response model for document upload."""

    document_id: UUID
    filename: str
    file_type: str
    file_size: int
    upload_date: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentProcessingResponse(BaseResponse):
    """Response model for document processing."""

    document_id: UUID
    text_length: int
    num_chunks: int
    chunks_stored: int
    processing_status: str

    model_config = ConfigDict(from_attributes=True)
