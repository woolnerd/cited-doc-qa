"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import documents, health, query
from app.core.config import settings
from app.core.exceptions import RAGChatbotException
from app.core.logging import get_logger, setup_logging

# Setup logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # Validate API keys on startup
    try:
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            logger.warning("Supabase credentials not configured")

        if not settings.GOOGLE_API_KEY:
            logger.warning("Google API key not configured")

        if not settings.COHERE_API_KEY:
            logger.warning("Cohere API key not configured")

        if not settings.OPENROUTER_API_KEY:
            logger.warning("OpenRouter API key not configured")

        logger.info("API keys validated successfully")
    except Exception as e:
        logger.error(f"Error validating API keys: {e}")

    yield

    # Shutdown
    logger.info("Shutting down application")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="A production-grade RAG chatbot with contextual chunking, hybrid search, and Claude integration.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(RAGChatbotException)
async def ragchatbot_exception_handler(
    request: Request, exc: RAGChatbotException
) -> JSONResponse:
    """Handle custom RAGChatbot exceptions.

    Args:
        request: The request that caused the exception
        exc: The exception instance

    Returns:
        JSON response with error details
    """
    logger.error(f"RAGChatbot exception: {exc.message}", exc_info=True)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.__class__.__name__,
            "detail": exc.message,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle general exceptions.

    Args:
        request: The request that caused the exception
        exc: The exception instance

    Returns:
        JSON response with error details
    """
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "InternalServerError",
            "detail": "An unexpected error occurred",
            "status_code": 500,
        },
    )


# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(query.router, prefix="/api", tags=["Query"])


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests.

    Args:
        request: The incoming request
        call_next: The next middleware/handler

    Returns:
        Response from the next handler
    """
    logger.info(f"{request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # nosec B104 - binding to all interfaces for dev
        port=8000,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
