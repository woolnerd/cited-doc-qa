"""Document upload and management endpoints."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.dependencies import SupabaseClient
from app.core.exceptions import FileValidationError
from app.core.logging import get_logger
from app.models.base import DocumentMetadata, DocumentUploadResponse

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
