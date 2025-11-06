"""Query enhancement service for improving search with conversation context."""

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class QueryEnhancementService:
    """Service for enhancing queries using conversation context and LLM.

    This service improves search quality by:
    1. Resolving referential language ("that", "this", "it")
    2. Adding context from conversation history
    3. Expanding abbreviations and synonyms
    4. Reformulating vague queries into specific searchable terms
    """

    def __init__(self, openrouter_api_key: str | None = None):
        """Initialize the query enhancement service.

        Args:
            openrouter_api_key: OpenRouter API key (uses settings if None)
        """
        self.api_key = openrouter_api_key or settings.OPENROUTER_API_KEY
        self.model = settings.LLM_MODEL
        self.base_url = settings.OPENROUTER_BASE_URL

    def enhance_query(
        self,
        query: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        """Enhance a query using conversation context.

        Args:
            query: Original user query
            conversation_history: Previous conversation messages [{"role": "user/assistant", "content": "..."}]

        Returns:
            Enhanced query string optimized for search
        """
        # If no conversation history or query is already detailed, return as-is
        if not conversation_history or len(query.split()) > 8:
            logger.info(f"No enhancement needed for query: '{query[:50]}...'")
            return query

        try:
            logger.info(
                f"Enhancing query: '{query[:50]}...' with {len(conversation_history)} messages"
            )

            # Build prompt for LLM
            enhanced = self._call_llm_for_enhancement(query, conversation_history)

            logger.info(f"Enhanced query: '{query[:50]}...' → '{enhanced[:50]}...'")
            return enhanced

        except Exception as e:
            logger.error(
                f"Query enhancement failed: {e}, using original query", exc_info=True
            )
            # Fallback to original query if enhancement fails
            return query

    def _call_llm_for_enhancement(
        self,
        query: str,
        conversation_history: list[dict[str, str]],
    ) -> str:
        """Call LLM to enhance the query.

        Args:
            query: Original query
            conversation_history: Conversation context

        Returns:
            Enhanced query string
        """
        import httpx

        # Build conversation context summary
        context_summary = self._build_context_summary(conversation_history)

        # Create enhancement prompt
        system_prompt = """You are a query enhancement assistant for a company knowledge base search system.

Your task: Rewrite user queries to be more specific and searchable by:
1. Resolving references like "that", "this", "it" using conversation context
2. Adding relevant context ONLY when the query is a follow-up to the same topic
3. Expanding vague terms into specific searchable phrases
4. Keeping the query concise (max 15 words)

IMPORTANT RULES:
- Only output the enhanced query, nothing else
- Don't add quotes or explanations
- Keep it natural and searchable
- If the query is already clear and specific, return it unchanged

TOPIC DETECTION:
- If query mentions a NEW specific topic (e.g., "remote work policy" after discussing "vacation policy"), treat as a NEW query - don't add previous topic context
- If query is vague follow-up (e.g., "how many days?", "what about that?"), ADD context from previous topic
- If query shifts to related but different topic (e.g., "sick leave" after "vacation"), keep it clean - these are parallel topics

Examples:
- "vacation policy" → "how many days?" = "how many vacation days allowed"
- "vacation policy" → "remote work policy" = "remote work policy" (NEW topic, no contamination)
- "electrical bill" → "capcut bill" = "capcut bill" (DIFFERENT bills, don't merge)"""

        user_prompt = f"""Conversation context:
{context_summary}

Current query: {query}

Enhanced query:"""

        # Call OpenRouter API
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 100,
                },
            )
            response.raise_for_status()

            result = response.json()
            enhanced_query: str = result["choices"][0]["message"]["content"].strip()

            # Clean up any quotes or extra formatting
            enhanced_query = enhanced_query.strip('"').strip("'").strip()

            return enhanced_query

    def _build_context_summary(
        self,
        conversation_history: list[dict[str, str]],
        max_messages: int = 4,
    ) -> str:
        """Build a concise summary of conversation context.

        Args:
            conversation_history: Full conversation history
            max_messages: Maximum number of recent messages to include

        Returns:
            Formatted context summary
        """
        # Take only the most recent messages
        recent = conversation_history[-max_messages:]

        lines = []
        for msg in recent:
            role = msg["role"].capitalize()
            content = msg["content"][:150]  # Truncate long messages
            if len(msg["content"]) > 150:
                content += "..."
            lines.append(f"{role}: {content}")

        return "\n".join(lines)
