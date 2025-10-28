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


class QueryRequest(BaseModel):
    """Request model for query endpoint."""

    query: str = Field(..., min_length=1, max_length=1000, description="User query")
    top_k: int = Field(
        default=5, ge=1, le=20, description="Number of results to return"
    )
    document_id: UUID | None = Field(
        default=None, description="Optional: Search within specific document"
    )

    model_config = ConfigDict(from_attributes=True)


class SearchResult(BaseModel):
    """Search result with scores and metadata."""

    chunk_id: str
    document_id: UUID
    document_name: str
    chunk_index: int
    content: str
    citation_num: int
    rerank_score: float | None = None
    rrf_score: float | None = None
    vector_score: float | None = None
    fulltext_score: float | None = None

    model_config = ConfigDict(from_attributes=True)


class QueryMetadata(BaseModel):
    """Metadata about query processing."""

    query: str
    results_count: int
    model: str
    temperature: float
    tokens_used: dict[str, int]
    timing: dict[str, float]
    used_fallback: bool = False

    model_config = ConfigDict(from_attributes=True)


class QueryResponse(BaseResponse):
    """Response model for query endpoint."""

    answer: str
    sources: list[SearchResult]
    metadata: QueryMetadata

    model_config = ConfigDict(from_attributes=True)


class DocumentListItem(BaseModel):
    """Document item in list response."""

    id: UUID
    filename: str
    file_type: str
    upload_date: datetime
    chunk_count: int
    status: str = "ready"  # ready, processing, failed
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseResponse):
    """Response model for documents list endpoint."""

    documents: list[DocumentListItem]
    total_count: int

    model_config = ConfigDict(from_attributes=True)


class DocumentDeleteResponse(BaseResponse):
    """Response model for document deletion."""

    document_id: UUID
    chunks_deleted: int

    model_config = ConfigDict(from_attributes=True)
