# Development Guide

This guide covers the development workflow, code quality standards, and best practices for the RAG chatbot project.

## Table of Contents

- [Getting Started](#getting-started)
- [Code Quality Standards](#code-quality-standards)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Git Workflow](#git-workflow)

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- Make (optional but recommended)

### Initial Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/woolnerd/production-rag-system.git
   cd production-rag-system
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   make install-dev
   # Or: pip install -r backend/requirements.txt && pip install pre-commit
   ```

4. **Set up pre-commit hooks:**
   ```bash
   make setup-hooks
   # Or: pre-commit install
   ```

5. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

## Code Quality Standards

This project enforces strict code quality standards using automated tools.

### Tools

- **Black**: Code formatting (88 character line length)
- **Ruff**: Fast Python linter (replaces flake8, isort, etc.)
- **Mypy**: Static type checking
- **Bandit**: Security vulnerability scanner
- **pytest**: Testing framework with coverage

### Running Quality Checks

```bash
# Format code
make format

# Lint code
make lint

# Auto-fix linting issues
make lint-fix

# Type check
make type-check

# Run all checks
make check-all
```

### Pre-commit Hooks

Pre-commit hooks run automatically before each commit. To run manually:

```bash
# Run on staged files
pre-commit run

# Run on all files
make pre-commit-all
```

If pre-commit hooks fail:
1. Review the changes made by the hooks
2. Stage the changes: `git add .`
3. Commit again

### Code Style Guidelines

#### Python Style

- **Line length**: 88 characters (Black default)
- **Imports**: Sorted by Ruff (stdlib → third-party → local)
- **Type hints**: Use type hints for function parameters and returns
- **Docstrings**: Google-style docstrings for public functions/classes

**Example:**

```python
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

from app.core.config import settings


def process_document(
    filename: str,
    content: bytes,
    file_type: Optional[str] = None
) -> dict:
    """Process an uploaded document.

    Args:
        filename: Original filename of the document
        content: File content as bytes
        file_type: Optional file type (pdf, docx, txt)

    Returns:
        Dictionary with processing results including document_id

    Raises:
        HTTPException: If file type is unsupported or processing fails
    """
    if file_type not in ["pdf", "docx", "txt"]:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    # Processing logic here
    return {"document_id": "123", "status": "completed"}
```

#### Naming Conventions

- **Variables/Functions**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private methods**: `_leading_underscore`

#### Project Structure

```
backend/app/
├── api/          # API route handlers
├── core/         # Core functionality (config, dependencies)
├── models/       # Pydantic models (request/response schemas)
└── services/     # Business logic layer
```

## Development Workflow

### Daily Workflow

1. **Pull latest changes:**
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Create feature branch:**
   ```bash
   git checkout -b issue-N-feature-name
   ```

3. **Make changes and test:**
   ```bash
   # Write code...
   make format lint type-check test
   ```

4. **Commit with conventional commits:**
   ```bash
   git add .
   git commit -m "feat: add document upload endpoint"
   ```

5. **Push and create PR:**
   ```bash
   git push origin issue-N-feature-name
   gh pr create
   ```

### Conventional Commits

Use conventional commit format:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Test additions/changes
- `refactor:` - Code refactoring
- `chore:` - Maintenance tasks
- `ci:` - CI/CD changes

**Examples:**
```bash
feat: add Cohere reranking integration
fix: handle empty query in hybrid search
docs: update API documentation
test: add unit tests for chunking service
```

## Testing

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run unit tests only
make test-unit

# Run integration tests
make test-integration

# Run specific test file
pytest tests/unit/test_chunking.py -v

# Run tests matching pattern
pytest -k "test_upload" -v
```

### Writing Tests

#### Unit Tests

```python
import pytest
from unittest.mock import Mock, patch

from app.services.embedding import EmbeddingService


@pytest.fixture
def embedding_service():
    """Fixture providing EmbeddingService instance."""
    return EmbeddingService(api_key="test-key")


def test_embed_text(embedding_service):
    """Test embedding generation for single text."""
    with patch('app.services.embedding.genai.embed_content') as mock_embed:
        mock_embed.return_value.embedding = [0.1] * 768

        result = embedding_service.embed_text("test content")

        assert len(result) == 768
        assert isinstance(result[0], float)
        mock_embed.assert_called_once()
```

#### Integration Tests

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.integration
def test_document_upload_flow(client: TestClient, test_pdf):
    """Test complete document upload and processing flow."""
    # Upload document
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test.pdf", test_pdf, "application/pdf")}
    )
    assert response.status_code == 201
    doc_id = response.json()["document_id"]

    # Verify chunks created
    # ... integration test logic
```

### Test Coverage

Minimum coverage requirements:
- Overall: 80%
- Critical paths (document processing, search): 85%
- API endpoints: 90%

View coverage report:
```bash
make test-cov
open htmlcov/index.html
```

## Git Workflow

### Branch Naming

- Feature: `issue-N-short-description`
- Bugfix: `fix-N-short-description`
- Hotfix: `hotfix-description`

### Pull Request Process

1. **Create PR** with description referencing issue
2. **Ensure CI passes** (tests, linting, coverage)
3. **Request review** if working in a team
4. **Merge** using "Squash and merge"
5. **Delete branch** after merge

### Closing Issues

Use keywords in commits to auto-close issues:
- `closes #N`
- `fixes #N`
- `resolves #N`

**Example:**
```bash
git commit -m "feat: add hybrid search (closes #13)"
```

## Troubleshooting

### Pre-commit Hook Failures

**Black formatting fails:**
```bash
make format
git add .
git commit
```

**Ruff linting fails:**
```bash
make lint-fix
git add .
git commit
```

**Mypy type errors:**
- Add type hints to function signatures
- Use `# type: ignore` for unavoidable third-party issues

### Test Failures

**Import errors:**
```bash
pip install -e .
```

**Database connection errors:**
- Check `.env` file has correct `SUPABASE_URL` and `SUPABASE_KEY`
- Verify Supabase project is running

### Performance Issues

**Slow tests:**
```bash
# Run in parallel
pytest -n auto

# Skip slow tests
pytest -m "not slow"
```

## Best Practices

### Code Organization

- Keep functions small and focused (< 50 lines)
- Use type hints for all public functions
- Write docstrings for complex logic
- Avoid deep nesting (max 3 levels)

### Error Handling

```python
from fastapi import HTTPException

# Use specific exceptions
raise HTTPException(status_code=400, detail="Invalid file type")

# Log errors before raising
logger.error(f"Failed to process document: {error}")
raise HTTPException(status_code=500, detail="Processing failed")
```

### Async/Await

```python
# Use async for I/O operations
async def process_document(file: UploadFile) -> dict:
    content = await file.read()
    embedding = await embedding_service.embed(content)
    await db.store(embedding)
    return {"status": "success"}
```

### Configuration

```python
from app.core.config import settings

# Access config via settings object
api_key = settings.GOOGLE_API_KEY
max_file_size = settings.MAX_FILE_SIZE_MB
```

## Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Pytest Documentation](https://docs.pytest.org/)
- [Pre-commit Documentation](https://pre-commit.com/)

---

For questions or issues, open a GitHub issue or consult the team.
