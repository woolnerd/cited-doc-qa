"""LLM service using Claude via Openrouter."""

import time
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletion

from app.core.config import settings
from app.core.exceptions import DocumentProcessingError
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMService:
    """Service for generating answers using Claude via Openrouter."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        """Initialize the LLM service.

        Args:
            api_key: Openrouter API key (uses settings if None)
            base_url: Openrouter base URL (uses settings if None)

        Raises:
            DocumentProcessingError: If client initialization fails
        """
        try:
            self.api_key = api_key or settings.OPENROUTER_API_KEY
            self.base_url = base_url or settings.OPENROUTER_BASE_URL
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            self.model = settings.LLM_MODEL
            self.temperature = settings.LLM_TEMPERATURE
            self.max_tokens = settings.LLM_MAX_TOKENS
            logger.info(f"LLM service initialized with model: {self.model}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}", exc_info=True)
            raise DocumentProcessingError(
                f"Failed to initialize LLM client: {e}"
            ) from e

    def _format_context(self, results: list[dict[str, Any]]) -> str:
        """Format search results into context for the LLM.

        Args:
            results: Reranked search results

        Returns:
            Formatted context string with citations
        """
        if not results:
            return "No relevant information found."

        context_parts = []
        for idx, result in enumerate(results):
            # Use contextual content if available, otherwise use content
            content = result.get("contextual_content") or result.get("content", "")

            # Get document metadata for citation
            metadata = result.get("metadata", {})
            doc_name = metadata.get("document_name", "Unknown Document")
            chunk_index = metadata.get("chunk_index", 0)

            # Format: [Citation 1] Content from doc_name (chunk X)
            citation_num = idx + 1
            context_parts.append(
                f"[{citation_num}] {content}\n(Source: {doc_name}, chunk {chunk_index + 1})"
            )

        return "\n\n".join(context_parts)

    def _create_system_prompt(self) -> str:
        """Create the system prompt for the RAG chatbot.

        Returns:
            System prompt string
        """
        return """You are a helpful AI assistant that answers questions based on the provided context from documents.

Your role:
- Answer questions accurately using only the information from the provided context
- Include citations [1], [2], etc. when referencing specific information
- If the context doesn't contain enough information to answer fully, say so
- Be concise but thorough
- Maintain a professional and helpful tone

Important:
- Do not make up information that's not in the context
- If you're uncertain, acknowledge it
- Use citations to help users verify information"""

    def generate_answer(
        self,
        query: str,
        search_results: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Generate an answer to the query using search results as context.

        Args:
            query: User's question
            search_results: Reranked search results for context
            temperature: Override default temperature (0.0-1.0)
            max_tokens: Override default max tokens

        Returns:
            Dictionary with answer and metadata

        Raises:
            DocumentProcessingError: If answer generation fails
        """
        try:
            temperature = temperature if temperature is not None else self.temperature
            max_tokens = max_tokens if max_tokens is not None else self.max_tokens

            logger.info(
                f"Generating answer for query: '{query[:50]}...' with {len(search_results)} context chunks"
            )

            # Format context from search results
            context = self._format_context(search_results)

            # Create messages
            system_prompt = self._create_system_prompt()
            user_message = f"""Context from documents:

{context}

Question: {query}

Please provide a comprehensive answer based on the context above, including citations."""

            start_time = time.time()

            # Call LLM API
            response: ChatCompletion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            generation_time = time.time() - start_time

            # Extract answer
            answer = response.choices[0].message.content or ""

            # Get token usage
            usage = response.usage
            tokens_used = {
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
            }

            logger.info(
                f"Answer generated in {generation_time:.3f}s, tokens: {tokens_used['total_tokens']}"
            )

            # Extract cited sources from search results
            cited_sources = [
                {
                    "citation_num": idx + 1,
                    "chunk_id": result["chunk_id"],
                    "document_id": result["document_id"],
                    "document_name": result.get("metadata", {}).get(
                        "document_name", "Unknown"
                    ),
                    "chunk_index": result.get("metadata", {}).get("chunk_index", 0),
                    "rerank_score": result.get("rerank_score"),
                }
                for idx, result in enumerate(search_results)
            ]

            return {
                "answer": answer,
                "sources": cited_sources,
                "metadata": {
                    "query": query,
                    "model": self.model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "tokens_used": tokens_used,
                    "context_chunks": len(search_results),
                    "timing": {
                        "generation_ms": round(generation_time * 1000, 2),
                    },
                    "finish_reason": response.choices[0].finish_reason,
                },
            }

        except Exception as e:
            logger.error(f"Failed to generate answer: {e}", exc_info=True)
            raise DocumentProcessingError(f"Failed to generate answer: {e}") from e

    def generate_answer_with_retry(
        self,
        query: str,
        search_results: list[dict[str, Any]],
        max_retries: int = 3,
        retry_delay: float = 1.0,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Generate answer with retry logic.

        Args:
            query: User's question
            search_results: Reranked search results for context
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries (exponential backoff)
            temperature: Override default temperature
            max_tokens: Override default max tokens

        Returns:
            Dictionary with answer and metadata

        Raises:
            DocumentProcessingError: If all retries fail
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                return self.generate_answer(
                    query=query,
                    search_results=search_results,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Answer generation failed on attempt {attempt + 1}/{max_retries}: {e}"
                )

                if attempt < max_retries - 1:
                    delay = retry_delay * (2**attempt)
                    logger.info(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)

        # All retries failed
        logger.error(f"Answer generation failed after {max_retries} attempts")
        raise DocumentProcessingError(
            f"Answer generation failed after {max_retries} attempts: {last_error}"
        ) from last_error
