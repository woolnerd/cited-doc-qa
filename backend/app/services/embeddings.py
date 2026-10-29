"""Embedding service using Google Gemini."""

import google.generativeai as genai
import httpx

from app.core.config import settings
from app.core.exceptions import DocumentProcessingError, ExternalAPIError
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """Service for generating embeddings using Google Gemini."""

    @staticmethod
    def _translate_provider_error(error: object) -> ExternalAPIError | None:
        """Map provider quota/rate-limit failures to a friendly app error."""
        status_code = getattr(error, "status_code", None) or getattr(
            error, "code", None
        )
        message = str(error).lower()

        is_quota_or_rate_limit = (
            status_code == 429
            or "429" in message
            or "quota" in message
            or "rate limit" in message
            or "rate-limits" in message
            or "resource_exhausted" in message
        )
        if not is_quota_or_rate_limit:
            return None

        return ExternalAPIError(
            "Embedding provider",
            "The document analysis service has reached its configured quota. Please try again later.",
            status_code=429,
        )

    def __init__(self):
        """Initialize the embedding service with Google API."""
        try:
            self.provider = settings.EMBEDDING_PROVIDER.lower()
            self.model_name = settings.EMBEDDING_MODEL
            self.openrouter_base_url = settings.OPENROUTER_BASE_URL.rstrip("/")
            self.openrouter_api_key = settings.OPENROUTER_API_KEY

            if self.provider == "gemini":
                genai.configure(api_key=settings.GOOGLE_API_KEY)
            elif self.provider != "openrouter":
                raise DocumentProcessingError(
                    f"Unsupported embedding provider: {settings.EMBEDDING_PROVIDER}"
                )

            logger.info(
                f"Initialized embedding service with provider={self.provider}, model={self.model_name}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize embedding service: {e}")
            raise DocumentProcessingError(
                "Failed to initialize embedding service"
            ) from e

    def _openrouter_embeddings(self, input_texts: str | list[str]) -> list[list[float]]:
        """Generate embeddings through OpenRouter's embeddings endpoint."""
        try:
            response = httpx.post(
                f"{self.openrouter_base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_name,
                    "input": input_texts,
                    "encoding_format": "float",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            return [item["embedding"] for item in response.json()["data"]]
        except httpx.HTTPStatusError as e:
            logger.error(
                f"OpenRouter embedding request failed: HTTP {e.response.status_code}",
                exc_info=True,
            )
            provider_error = self._translate_provider_error(e.response)
            if provider_error is not None:
                raise provider_error from e
            raise DocumentProcessingError("Failed to generate embedding") from e
        except ExternalAPIError:
            raise
        except Exception as e:
            logger.error(f"OpenRouter embedding request failed: {e}", exc_info=True)
            provider_error = self._translate_provider_error(e)
            if provider_error is not None:
                raise provider_error from e
            raise DocumentProcessingError("Failed to generate embedding") from e

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

            if self.provider == "openrouter":
                embedding = self._openrouter_embeddings(text)[0]
            else:
                result = genai.embed_content(
                    model=self.model_name,
                    content=text,
                    task_type="retrieval_document",
                )
                embedding = result["embedding"]

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
        except ExternalAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}", exc_info=True)
            provider_error = self._translate_provider_error(e)
            if provider_error is not None:
                raise provider_error from e
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

            if self.provider == "openrouter":
                embeddings: list[list[float]] = []
                non_empty_texts = []
                non_empty_indexes = []

                for index, text in enumerate(texts):
                    if not text or not text.strip():
                        logger.warning("Skipping empty text in batch")
                        embeddings.append([0.0] * settings.EMBEDDING_DIMENSIONS)
                    else:
                        embeddings.append([])
                        non_empty_texts.append(text)
                        non_empty_indexes.append(index)

                if non_empty_texts:
                    generated_embeddings = self._openrouter_embeddings(non_empty_texts)
                    for index, embedding in zip(
                        non_empty_indexes, generated_embeddings, strict=True
                    ):
                        embeddings[index] = embedding

                logger.info(f"Generated {len(embeddings)} embeddings successfully")
                return embeddings

            embeddings = []

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
        except ExternalAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}", exc_info=True)
            provider_error = self._translate_provider_error(e)
            if provider_error is not None:
                raise provider_error from e
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

            if self.provider == "openrouter":
                embedding = self._openrouter_embeddings(query)[0]
            else:
                result = genai.embed_content(
                    model=self.model_name,
                    content=query,
                    task_type="retrieval_query",
                )
                embedding = result["embedding"]

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
        except ExternalAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}", exc_info=True)
            provider_error = self._translate_provider_error(e)
            if provider_error is not None:
                raise provider_error from e
            raise DocumentProcessingError(
                f"Failed to generate query embedding: {e}"
            ) from e
