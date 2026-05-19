"""Custom exception classes for the application."""


class RAGChatbotException(Exception):
    """Base exception for RAG Chatbot application."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class DocumentProcessingError(RAGChatbotException):
    """Raised when document processing fails."""

    def __init__(self, message: str = "Document processing failed"):
        super().__init__(message, status_code=422)


class FileValidationError(RAGChatbotException):
    """Raised when file validation fails."""

    def __init__(self, message: str = "Invalid file"):
        super().__init__(message, status_code=400)


class DemoLimitError(RAGChatbotException):
    """Raised when a public demo usage limit is exceeded."""

    def __init__(
        self,
        message: str = "This public demo limit has been reached.",
        status_code: int = 429,
        limit_type: str | None = None,
    ):
        self.limit_type = limit_type
        super().__init__(message, status_code=status_code)


class EmbeddingError(RAGChatbotException):
    """Raised when embedding generation fails."""

    def __init__(self, message: str = "Embedding generation failed"):
        super().__init__(message, status_code=500)


class SearchError(RAGChatbotException):
    """Raised when search operation fails."""

    def __init__(self, message: str = "Search operation failed"):
        super().__init__(message, status_code=500)


class DatabaseError(RAGChatbotException):
    """Raised when database operation fails."""

    def __init__(self, message: str = "Database operation failed"):
        super().__init__(message, status_code=500)


class ExternalAPIError(RAGChatbotException):
    """Raised when external API call fails."""

    def __init__(self, service: str, message: str = "External API error"):
        self.service = service
        super().__init__(f"{service}: {message}", status_code=503)
