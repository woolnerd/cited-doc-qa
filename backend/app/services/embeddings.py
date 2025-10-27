"""Embedding service using Google Gemini."""

import google.generativeai as genai

from app.core.config import settings
from app.core.exceptions import DocumentProcessingError
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """Service for generating embeddings using Google Gemini."""

    def __init__(self):
        """Initialize the embedding service with Google API."""
        try:
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            self.model_name = settings.EMBEDDING_MODEL
            logger.info(f"Initialized embedding service with model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize embedding service: {e}")
            raise DocumentProcessingError(
                "Failed to initialize embedding service"
            ) from e

    def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to generate embedding for

        Returns:
            Embedding vector as list of floats

        Raises:
            DocumentProcessingError: If embedding generation fails
        """
        try:
            if not text or not text.strip():
                raise DocumentProcessingError(
                    "Cannot generate embedding for empty text"
                )

            result = genai.embed_content(
                model=self.model_name,
                content=text,
                task_type="retrieval_document",
            )

            embedding: list[float] = result["embedding"]

            # Validate embedding dimensions
            if len(embedding) != settings.EMBEDDING_DIMENSIONS:
                raise DocumentProcessingError(
                    f"Expected {settings.EMBEDDING_DIMENSIONS} dimensions, "
                    f"got {len(embedding)}"
                )

            logger.debug(f"Generated embedding with {len(embedding)} dimensions")
            return embedding

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}", exc_info=True)
            raise DocumentProcessingError(f"Failed to generate embedding: {e}") from e

    def generate_embeddings_batch(
        self, texts: list[str], batch_size: int = 100
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts in batches.

        Args:
            texts: List of texts to generate embeddings for
            batch_size: Number of texts to process in each batch

        Returns:
            List of embedding vectors

        Raises:
            DocumentProcessingError: If embedding generation fails
        """
        try:
            if not texts:
                raise DocumentProcessingError(
                    "Cannot generate embeddings for empty list"
                )

            embeddings: list[list[float]] = []

            # Process in batches to avoid API limits
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                logger.info(
                    f"Processing batch {i // batch_size + 1} "
                    f"({len(batch)} texts, total {len(texts)})"
                )

                for text in batch:
                    if not text or not text.strip():
                        logger.warning("Skipping empty text in batch")
                        # Add zero vector for empty texts to maintain index alignment
                        embeddings.append([0.0] * settings.EMBEDDING_DIMENSIONS)
                        continue

                    embedding = self.generate_embedding(text)
                    embeddings.append(embedding)

            logger.info(f"Generated {len(embeddings)} embeddings successfully")
            return embeddings

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}", exc_info=True)
            raise DocumentProcessingError(
                f"Failed to generate batch embeddings: {e}"
            ) from e

    def generate_query_embedding(self, query: str) -> list[float]:
        """Generate embedding for a search query.

        Args:
            query: Search query text

        Returns:
            Embedding vector as list of floats

        Raises:
            DocumentProcessingError: If embedding generation fails
        """
        try:
            if not query or not query.strip():
                raise DocumentProcessingError(
                    "Cannot generate embedding for empty query"
                )

            result = genai.embed_content(
                model=self.model_name,
                content=query,
                task_type="retrieval_query",
            )

            embedding: list[float] = result["embedding"]

            # Validate embedding dimensions
            if len(embedding) != settings.EMBEDDING_DIMENSIONS:
                raise DocumentProcessingError(
                    f"Expected {settings.EMBEDDING_DIMENSIONS} dimensions, "
                    f"got {len(embedding)}"
                )

            logger.debug(f"Generated query embedding with {len(embedding)} dimensions")
            return embedding

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}", exc_info=True)
            raise DocumentProcessingError(
                f"Failed to generate query embedding: {e}"
            ) from e
