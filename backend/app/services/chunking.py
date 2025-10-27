"""Contextual chunking service for document text."""

import re
from typing import Any

import tiktoken

from app.core.config import settings
from app.core.exceptions import DocumentProcessingError
from app.core.logging import get_logger

logger = get_logger(__name__)


class ChunkingService:
    """Service for splitting text into contextual chunks."""

    def __init__(self):
        """Initialize the chunking service with tiktoken encoder."""
        try:
            # Use cl100k_base encoding (used by GPT-3.5/GPT-4)
            self.encoder = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.error(f"Failed to initialize tiktoken encoder: {e}")
            raise DocumentProcessingError(
                "Failed to initialize text chunking service"
            ) from e

    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in text.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        return len(self.encoder.encode(text))

    def create_contextual_chunk(
        self, chunk_text: str, document_metadata: dict[str, Any]
    ) -> str:
        """Add document context to a chunk.

        Args:
            chunk_text: The chunk text
            document_metadata: Document metadata (filename, etc.)

        Returns:
            Chunk text with prepended context
        """
        filename = document_metadata.get("filename", "Unknown")
        file_type = document_metadata.get("file_type", "unknown")

        context = f"Document: {filename} (Type: {file_type})\n\n"
        return context + chunk_text

    def split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences for better chunk boundaries.

        Args:
            text: Text to split

        Returns:
            List of sentences
        """
        # Simple sentence splitting regex
        # Handles common sentence endings: . ! ?
        sentence_pattern = r"(?<=[.!?])\s+(?=[A-Z])"
        sentences = re.split(sentence_pattern, text)

        # Clean up sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences

    def chunk_text(
        self,
        text: str,
        document_metadata: dict[str, Any],
        min_chunk_size: int | None = None,
        max_chunk_size: int | None = None,
    ) -> list[dict[str, Any]]:
        """Split text into contextual chunks.

        Args:
            text: Text to chunk
            document_metadata: Document metadata to add as context
            min_chunk_size: Minimum chunk size in tokens (default from settings)
            max_chunk_size: Maximum chunk size in tokens (default from settings)

        Returns:
            List of chunks with metadata

        Raises:
            DocumentProcessingError: If chunking fails
        """
        try:
            min_size = min_chunk_size or settings.CHUNK_SIZE_MIN
            max_size = max_chunk_size or settings.CHUNK_SIZE_MAX

            if not text or not text.strip():
                raise DocumentProcessingError("Cannot chunk empty text")

            # Split into sentences for better boundaries
            sentences = self.split_into_sentences(text)

            if not sentences:
                # Fallback: treat entire text as one sentence
                sentences = [text]

            chunks: list[dict[str, Any]] = []
            current_chunk: list[str] = []
            current_token_count = 0

            # Calculate context overhead
            sample_context = self.create_contextual_chunk("", document_metadata)
            context_tokens = self.count_tokens(sample_context)

            logger.info(
                f"Chunking text with {len(sentences)} sentences, "
                f"context overhead: {context_tokens} tokens"
            )

            for sentence in sentences:
                sentence_tokens = self.count_tokens(sentence)

                # If single sentence exceeds max, split it by words
                if sentence_tokens + context_tokens > max_size:
                    # Save current chunk if it has content
                    if current_chunk:
                        chunk_text = " ".join(current_chunk)
                        contextual_chunk = self.create_contextual_chunk(
                            chunk_text, document_metadata
                        )
                        chunks.append(
                            {
                                "content": chunk_text,
                                "contextual_content": contextual_chunk,
                                "token_count": self.count_tokens(contextual_chunk),
                                "chunk_index": len(chunks),
                            }
                        )
                        current_chunk = []
                        current_token_count = 0

                    # Split long sentence into smaller chunks
                    words = sentence.split()
                    word_chunk: list[str] = []
                    word_token_count = 0

                    for word in words:
                        word_tokens = self.count_tokens(word + " ")

                        if word_token_count + word_tokens + context_tokens > max_size:
                            if word_chunk:
                                chunk_text = " ".join(word_chunk)
                                contextual_chunk = self.create_contextual_chunk(
                                    chunk_text, document_metadata
                                )
                                chunks.append(
                                    {
                                        "content": chunk_text,
                                        "contextual_content": contextual_chunk,
                                        "token_count": self.count_tokens(
                                            contextual_chunk
                                        ),
                                        "chunk_index": len(chunks),
                                    }
                                )
                                word_chunk = []
                                word_token_count = 0

                        word_chunk.append(word)
                        word_token_count += word_tokens

                    if word_chunk:
                        chunk_text = " ".join(word_chunk)
                        contextual_chunk = self.create_contextual_chunk(
                            chunk_text, document_metadata
                        )
                        chunks.append(
                            {
                                "content": chunk_text,
                                "contextual_content": contextual_chunk,
                                "token_count": self.count_tokens(contextual_chunk),
                                "chunk_index": len(chunks),
                            }
                        )

                    continue

                # Check if adding this sentence would exceed max_size
                if (
                    current_token_count + sentence_tokens + context_tokens > max_size
                    and current_chunk
                ):
                    # Save current chunk
                    chunk_text = " ".join(current_chunk)
                    contextual_chunk = self.create_contextual_chunk(
                        chunk_text, document_metadata
                    )
                    chunks.append(
                        {
                            "content": chunk_text,
                            "contextual_content": contextual_chunk,
                            "token_count": self.count_tokens(contextual_chunk),
                            "chunk_index": len(chunks),
                        }
                    )
                    current_chunk = []
                    current_token_count = 0

                # Add sentence to current chunk
                current_chunk.append(sentence)
                current_token_count += sentence_tokens

                # If we've reached min_size and next sentence would exceed max_size,
                # create a chunk
                if current_token_count + context_tokens >= min_size:
                    # Look ahead to see if we should end the chunk here
                    if len(current_chunk) > 0:
                        # Check if this is a good stopping point
                        # (we can add more sophisticated logic here later)
                        pass

            # Add remaining content as final chunk
            if current_chunk:
                chunk_text = " ".join(current_chunk)
                contextual_chunk = self.create_contextual_chunk(
                    chunk_text, document_metadata
                )
                chunks.append(
                    {
                        "content": chunk_text,
                        "contextual_content": contextual_chunk,
                        "token_count": self.count_tokens(contextual_chunk),
                        "chunk_index": len(chunks),
                    }
                )

            logger.info(
                f"Created {len(chunks)} chunks from {self.count_tokens(text)} tokens"
            )

            return chunks

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(f"Chunking failed: {e}", exc_info=True)
            raise DocumentProcessingError(f"Failed to chunk text: {e}") from e
