"""Document upload and management endpoints."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.dependencies import SupabaseClient
from app.core.exceptions import DocumentProcessingError, FileValidationError
from app.core.logging import get_logger
from app.models.base import (
    DocumentDeleteResponse,
    DocumentListItem,
    DocumentListResponse,
    DocumentMetadata,
    DocumentProcessingResponse,
    DocumentUploadResponse,
)
from app.services.document_processor import DocumentProcessor

logger = get_logger(__name__)

router = APIRouter()

# Allowed file types and their extensions
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}

# Maximum file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes


def validate_file(file: UploadFile) -> None:
    """Validate uploaded file type and size.

    Args:
        file: The uploaded file

    Raises:
        FileValidationError: If file validation fails
    """
    # Check filename exists
    if not file.filename:
        raise FileValidationError("Filename is required")

    # Check file extension
    file_ext = (
        "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    )
    if file_ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Check MIME type if available
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        logger.warning(
            f"File {file.filename} has unexpected MIME type: {file.content_type}"
        )

    # Check file size
    if file.size and file.size > MAX_FILE_SIZE:
        size_mb = file.size / (1024 * 1024)
        max_size_mb = MAX_FILE_SIZE / (1024 * 1024)
        raise FileValidationError(
            f"File size ({size_mb:.2f}MB) exceeds maximum allowed size ({max_size_mb}MB)"
        )


def get_file_type(filename: str) -> str:
    """Extract file type from filename.

    Args:
        filename: The filename

    Returns:
        File type without the dot (e.g., 'pdf', 'docx', 'txt')
    """
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    supabase: SupabaseClient = None,
) -> DocumentUploadResponse:
    """Upload a document for processing.

    Args:
        file: The file to upload
        supabase: Supabase client (injected dependency)

    Returns:
        Document upload confirmation with metadata

    Raises:
        FileValidationError: If file validation fails
        HTTPException: If document storage fails
    """
    logger.info(f"Received upload request for file: {file.filename}")

    # Validate file
    validate_file(file)

    # Read file content to get actual size
    file_content = await file.read()
    file_size = len(file_content)

    # Validate size again with actual content
    if file_size > MAX_FILE_SIZE:
        size_mb = file_size / (1024 * 1024)
        max_size_mb = MAX_FILE_SIZE / (1024 * 1024)
        raise FileValidationError(
            f"File size ({size_mb:.2f}MB) exceeds maximum allowed size ({max_size_mb}MB)"
        )

    # Reset file pointer for potential future reads
    await file.seek(0)

    # Extract file metadata
    file_type = get_file_type(file.filename)
    upload_date = datetime.now(UTC)

    # Store document metadata in Supabase
    try:
        result = (
            supabase.table("documents")
            .insert(
                {
                    "filename": file.filename,
                    "file_type": file_type,
                    "upload_date": upload_date.isoformat(),
                    "metadata": {
                        "file_size": file_size,
                        "content_type": file.content_type,
                    },
                }
            )
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store document metadata",
            )

        document_data = result.data[0]
        document_id = UUID(document_data["id"])

        logger.info(f"Document uploaded successfully: {document_id}")

        return DocumentUploadResponse(
            success=True,
            message="Document uploaded successfully",
            document_id=document_id,
            filename=file.filename,
            file_type=file_type,
            file_size=file_size,
            upload_date=upload_date,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error storing document metadata: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store document",
        ) from e


@router.get("/{document_id}", response_model=DocumentMetadata)
async def get_document(
    document_id: UUID,
    supabase: SupabaseClient = None,
) -> DocumentMetadata:
    """Get document metadata by ID.

    Args:
        document_id: The document UUID
        supabase: Supabase client (injected dependency)

    Returns:
        Document metadata

    Raises:
        HTTPException: If document not found or retrieval fails
    """
    try:
        result = (
            supabase.table("documents").select("*").eq("id", str(document_id)).execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        document_data = result.data[0]

        return DocumentMetadata(
            id=UUID(document_data["id"]),
            filename=document_data["filename"],
            file_type=document_data["file_type"],
            upload_date=datetime.fromisoformat(document_data["upload_date"]),
            metadata=document_data.get("metadata", {}),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving document {document_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve document",
        ) from e


@router.post("/{document_id}/process", response_model=DocumentProcessingResponse)
async def process_document(
    document_id: UUID,
    file: UploadFile = File(...),
    supabase: SupabaseClient = None,
) -> DocumentProcessingResponse:
    """Process an uploaded document through the RAG pipeline.

    This endpoint:
    1. Extracts text from the document
    2. Chunks the text with contextual information
    3. Generates embeddings for each chunk
    4. Stores chunks and embeddings in the database

    Args:
        document_id: UUID of the uploaded document
        file: The uploaded file content
        supabase: Supabase client (injected dependency)

    Returns:
        Processing results with statistics

    Raises:
        HTTPException: If document doesn't exist or processing fails
    """
    try:
        # Verify document exists
        doc_result = (
            supabase.table("documents").select("*").eq("id", str(document_id)).execute()
        )

        if not doc_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        document_data = doc_result.data[0]
        filename = document_data["filename"]
        file_type = document_data["file_type"]

        # Read file content
        file_content = await file.read()

        # Process document through pipeline
        logger.info(f"Processing document {document_id}")
        processor = DocumentProcessor(supabase_client=supabase)

        result = processor.process_document(
            document_id=document_id,
            file_content=file_content,
            filename=filename,
            file_type=file_type,
        )

        return DocumentProcessingResponse(
            success=True,
            message="Document processed successfully",
            document_id=document_id,
            text_length=result["text_length"],
            num_chunks=result["num_chunks"],
            chunks_stored=result["chunks_stored"],
            processing_status=result["status"],
        )

    except HTTPException:
        raise
    except DocumentProcessingError as e:
        logger.error(f"Document processing failed for {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document processing failed: {str(e)}",
        ) from e
    except Exception as e:
        logger.error(
            f"Unexpected error processing document {document_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process document",
        ) from e


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    supabase: SupabaseClient = None,
) -> DocumentListResponse:
    """List all documents with their metadata and chunk counts.

    Args:
        supabase: Supabase client (injected dependency)

    Returns:
        List of all documents with metadata

    Raises:
        HTTPException: If retrieval fails
    """
    try:
        # Get all documents
        result = (
            supabase.table("documents")
            .select("*")
            .order("upload_date", desc=True)
            .execute()
        )

        documents = []
        for doc_data in result.data:
            # Get chunk count for this document
            chunk_result = (
                supabase.table("chunks")
                .select("id", count="exact")
                .eq("document_id", doc_data["id"])
                .execute()
            )

            chunk_count = chunk_result.count if chunk_result.count is not None else 0

            # Determine status based on chunk count
            doc_status = "ready" if chunk_count > 0 else "processing"

            documents.append(
                DocumentListItem(
                    id=UUID(doc_data["id"]),
                    filename=doc_data["filename"],
                    file_type=doc_data["file_type"],
                    upload_date=datetime.fromisoformat(doc_data["upload_date"]),
                    chunk_count=chunk_count,
                    status=doc_status,
                    metadata=doc_data.get("metadata", {}),
                )
            )

        logger.info(f"Retrieved {len(documents)} documents")

        return DocumentListResponse(
            success=True,
            message=f"Retrieved {len(documents)} documents",
            documents=documents,
            total_count=len(documents),
        )

    except Exception as e:
        logger.error(f"Error retrieving documents: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve documents",
        ) from e


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: UUID,
    supabase: SupabaseClient = None,
) -> DocumentDeleteResponse:
    """Delete a document and all its associated chunks.

    The database cascade delete will automatically remove all chunks
    associated with this document.

    Args:
        document_id: The document UUID to delete
        supabase: Supabase client (injected dependency)

    Returns:
        Deletion confirmation with statistics

    Raises:
        HTTPException: If document not found or deletion fails
    """
    try:
        # Check if document exists
        doc_result = (
            supabase.table("documents")
            .select("id")
            .eq("id", str(document_id))
            .execute()
        )

        if not doc_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        # Get chunk count before deletion
        chunk_result = (
            supabase.table("chunks")
            .select("id", count="exact")
            .eq("document_id", str(document_id))
            .execute()
        )

        chunks_to_delete = chunk_result.count if chunk_result.count is not None else 0

        # Delete document (chunks will be cascade deleted)
        delete_result = (
            supabase.table("documents").delete().eq("id", str(document_id)).execute()
        )

        if not delete_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete document",
            )

        logger.info(
            f"Deleted document {document_id} and {chunks_to_delete} associated chunks"
        )

        return DocumentDeleteResponse(
            success=True,
            message=f"Document deleted successfully with {chunks_to_delete} chunks",
            document_id=document_id,
            chunks_deleted=chunks_to_delete,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document {document_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document",
        ) from e
