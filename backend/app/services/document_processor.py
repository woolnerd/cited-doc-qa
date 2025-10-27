"""Document processing pipeline integrating extraction, chunking, and embedding."""

from typing import Any
from uuid import UUID

from supabase import Client

from app.core.exceptions import DocumentProcessingError
from app.core.logging import get_logger
from app.services.chunking import ChunkingService
from app.services.embeddings import EmbeddingService
from app.services.text_extraction import TextExtractor

logger = get_logger(__name__)


class DocumentProcessor:
    """Service for processing documents through the full RAG pipeline."""

    def __init__(
        self,
        supabase_client: Client,
        text_extractor: TextExtractor | None = None,
        chunking_service: ChunkingService | None = None,
        embedding_service: EmbeddingService | None = None,
    ):
        """Initialize the document processor with required services.

        Args:
            supabase_client: Supabase client for database operations
            text_extractor: Text extraction service (creates new if None)
            chunking_service: Chunking service (creates new if None)
            embedding_service: Embedding service (creates new if None)
        """
        self.supabase = supabase_client
        self.text_extractor = text_extractor or TextExtractor()
        self.chunking_service = chunking_service or ChunkingService()
        self.embedding_service = embedding_service or EmbeddingService()

    def process_document(
        self,
        document_id: UUID,
        file_content: bytes,
        filename: str,
        file_type: str,
    ) -> dict[str, Any]:
        """Process a document through the full pipeline.

        Args:
            document_id: UUID of the document in the database
            file_content: Raw file content as bytes
            filename: Name of the file
            file_type: Type of file (pdf, docx, txt)

        Returns:
            Processing result with statistics

        Raises:
            DocumentProcessingError: If any step in the pipeline fails
        """
        try:
            logger.info(f"Starting document processing for {document_id}")

            # Step 1: Extract text from document
            logger.info("Step 1: Extracting text...")
            extracted_text = self.text_extractor.extract_text(file_content, file_type)
            text_length = len(extracted_text)
            logger.info(f"Extracted {text_length} characters")

            # Step 2: Chunk the text with context
            logger.info("Step 2: Chunking text...")
            try:
                document_metadata = {"filename": filename, "file_type": file_type}
                chunks = self.chunking_service.chunk_text(
                    extracted_text, document_metadata
                )
                num_chunks = len(chunks)
                logger.info(f"Created {num_chunks} chunks")
            except Exception as e:
                logger.error(f"Chunking failed: {e}")
                raise DocumentProcessingError(f"Failed to process document: {e}") from e

            # Step 3: Generate embeddings for all chunks
            logger.info("Step 3: Generating embeddings...")
            try:
                chunk_texts = [chunk["contextual_content"] for chunk in chunks]
                embeddings = self.embedding_service.generate_embeddings_batch(
                    chunk_texts
                )
                logger.info(f"Generated {len(embeddings)} embeddings")
            except Exception as e:
                logger.error(f"Embedding generation failed: {e}")
                raise DocumentProcessingError(f"Failed to process document: {e}") from e

            # Step 4: Store chunks and embeddings in database
            logger.info("Step 4: Storing chunks in database...")
            stored_chunks = self._store_chunks(
                document_id=document_id,
                chunks=chunks,
                embeddings=embeddings,
            )

            logger.info(
                f"Document processing complete for {document_id}: "
                f"{num_chunks} chunks stored"
            )

            return {
                "document_id": str(document_id),
                "text_length": text_length,
                "num_chunks": num_chunks,
                "chunks_stored": stored_chunks,
                "status": "completed",
            }

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(
                f"Document processing failed for {document_id}: {e}", exc_info=True
            )
            raise DocumentProcessingError(f"Failed to process document: {e}") from e

    def _store_chunks(
        self,
        document_id: UUID,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> int:
        """Store document chunks and embeddings in Supabase.

        Args:
            document_id: UUID of the parent document
            chunks: List of chunk dictionaries with content and metadata
            embeddings: List of embedding vectors corresponding to chunks

        Returns:
            Number of chunks successfully stored

        Raises:
            DocumentProcessingError: If storage fails
        """
        try:
            if len(chunks) != len(embeddings):
                raise DocumentProcessingError(
                    f"Chunk count ({len(chunks)}) does not match "
                    f"embedding count ({len(embeddings)})"
                )

            # Prepare chunk records for batch insert
            chunk_records = []
            for chunk, embedding in zip(chunks, embeddings, strict=False):
                chunk_records.append(
                    {
                        "document_id": str(document_id),
                        "content": chunk["content"],
                        "contextual_content": chunk["contextual_content"],
                        "chunk_index": chunk["chunk_index"],
                        "embedding": embedding,
                        "metadata": {
                            "token_count": chunk["token_count"],
                            "content_length": len(chunk["content"]),
                            "contextual_length": len(chunk["contextual_content"]),
                        },
                    }
                )

            # Batch insert all chunks
            result = self.supabase.table("chunks").insert(chunk_records).execute()

            if not result.data:
                raise DocumentProcessingError("Failed to store chunks in database")

            stored_count = len(result.data)
            logger.info(f"Successfully stored {stored_count} chunks")

            return stored_count

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Failed to store chunks: {e}", exc_info=True)
            raise DocumentProcessingError(f"Failed to store chunks: {e}") from e
