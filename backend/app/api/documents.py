"""Document upload and management endpoints."""

import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from app.core.dependencies import Database
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
    *,
    file: UploadFile = File(...),
    session_id: str = Form(...),
    db: Database,
) -> DocumentUploadResponse:
    """Upload a document for processing.

    Args:
        file: The file to upload
        session_id: Session identifier for multi-user isolation
        db: Database service (injected dependency)

    Returns:
        Document upload confirmation with metadata

    Raises:
        FileValidationError: If file validation fails
        HTTPException: If document storage fails
    """
    logger.info(
        f"Received upload request for file: {file.filename} (session: {session_id})"
    )

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

    # Store document metadata in PostgreSQL
    try:
        metadata_json = json.dumps(
            {
                "file_size": file_size,
                "content_type": file.content_type,
            }
        )

        query = """
            INSERT INTO documents (filename, file_type, upload_date, session_id, metadata)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING id, filename, file_type, upload_date, session_id, metadata
        """

        result = await db.fetchrow(
            query, file.filename, file_type, upload_date, session_id, metadata_json
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store document metadata",
            )

        document_id = UUID(str(result["id"]))

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
    db: Database,
) -> DocumentMetadata:
    """Get document metadata by ID.

    Args:
        document_id: The document UUID
        db: Database service (injected dependency)

    Returns:
        Document metadata

    Raises:
        HTTPException: If document not found or retrieval fails
    """
    try:
        query = """
            SELECT id, filename, file_type, upload_date, metadata
            FROM documents
            WHERE id = $1
        """

        result = await db.fetchrow(query, document_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        # Parse metadata if it's a JSON string
        metadata = result["metadata"]
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}

        return DocumentMetadata(
            id=UUID(str(result["id"])),
            filename=result["filename"],
            file_type=result["file_type"],
            upload_date=result["upload_date"],
            metadata=metadata,
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
    *,
    file: UploadFile = File(...),
    db: Database,
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
        db: Database service (injected dependency)

    Returns:
        Processing results with statistics

    Raises:
        HTTPException: If document doesn't exist or processing fails
    """
    try:
        # Verify document exists
        query = "SELECT filename, file_type FROM documents WHERE id = $1"
        doc_result = await db.fetchrow(query, document_id)

        if not doc_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        filename = doc_result["filename"]
        file_type = doc_result["file_type"]

        # Read file content
        file_content = await file.read()

        # Process document through pipeline
        logger.info(f"Processing document {document_id}")
        processor = DocumentProcessor(db_service=db)

        result = await processor.process_document(
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
        # Delete the failed document from database
        try:
            await db.execute("DELETE FROM documents WHERE id = $1", document_id)
            logger.info(f"Deleted failed document {document_id}")
        except Exception as del_error:
            logger.error(f"Failed to delete document {document_id}: {del_error}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document processing failed: {str(e)}",
        ) from e
    except Exception as e:
        logger.error(
            f"Unexpected error processing document {document_id}: {e}", exc_info=True
        )
        # Delete the failed document from database
        try:
            await db.execute("DELETE FROM documents WHERE id = $1", document_id)
            logger.info(f"Deleted failed document {document_id}")
        except Exception as del_error:
            logger.error(f"Failed to delete document {document_id}: {del_error}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process document",
        ) from e


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    session_id: str = Query(...),
    *,
    db: Database,
) -> DocumentListResponse:
    """List documents for current session and global documents.

    Args:
        session_id: Session identifier (from query param)
        db: Database service (injected dependency)

    Returns:
        List of session + global documents with metadata

    Raises:
        HTTPException: If retrieval fails
    """
    try:
        # Get session documents + global documents with chunk counts
        query = """
            SELECT
                d.id,
                d.filename,
                d.file_type,
                d.upload_date,
                d.session_id,
                d.metadata,
                COUNT(c.id) as chunk_count
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
            WHERE d.session_id = $1 OR d.session_id = 'global'
            GROUP BY d.id, d.filename, d.file_type, d.upload_date, d.session_id, d.metadata
            ORDER BY d.upload_date DESC
        """

        results = await db.fetch(query, session_id)

        documents = []
        for row in results:
            chunk_count = row["chunk_count"] or 0

            # Determine status based on chunk count
            doc_status = "ready" if chunk_count > 0 else "processing"

            # Parse metadata if it's a JSON string
            metadata = row["metadata"]
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    metadata = {}

            documents.append(
                DocumentListItem(
                    id=UUID(str(row["id"])),
                    filename=row["filename"],
                    file_type=row["file_type"],
                    upload_date=row["upload_date"],
                    chunk_count=chunk_count,
                    session_id=row["session_id"],
                    status=doc_status,
                    metadata=metadata,
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
    session_id: str = Query(...),
    *,
    db: Database,
) -> DocumentDeleteResponse:
    """Delete a document and all its associated chunks.

    The database cascade delete will automatically remove all chunks
    associated with this document. Users can only delete their own
    session documents, not global documents.

    Args:
        document_id: The document UUID to delete
        session_id: Session identifier (from query param)
        db: Database service (injected dependency)

    Returns:
        Deletion confirmation with statistics

    Raises:
        HTTPException: If document not found, unauthorized, or deletion fails
    """
    try:
        # Check if document exists, get session_id and chunk count
        check_query = """
            SELECT
                d.id,
                d.session_id,
                COUNT(c.id) as chunk_count
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
            WHERE d.id = $1
            GROUP BY d.id, d.session_id
        """

        doc_result = await db.fetchrow(check_query, document_id)

        if not doc_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found",
            )

        doc_session_id = doc_result["session_id"]

        # Prevent deletion of global documents
        if doc_session_id == "global":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete global documents",
            )

        # Verify session ownership
        if doc_session_id != session_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete documents from other sessions",
            )

        chunks_to_delete = doc_result["chunk_count"] or 0

        # Delete document (chunks will be cascade deleted)
        delete_query = "DELETE FROM documents WHERE id = $1"
        await db.execute(delete_query, document_id)

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
