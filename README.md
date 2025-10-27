# RAG Chatbot Demo

[![CI](https://github.com/woolnerd/production-rag-system/actions/workflows/ci.yml/badge.svg)](https://github.com/woolnerd/production-rag-system/actions/workflows/ci.yml)
[![Deploy](https://github.com/woolnerd/production-rag-system/actions/workflows/deploy.yml/badge.svg)](https://github.com/woolnerd/production-rag-system/actions/workflows/deploy.yml)
[![codecov](https://codecov.io/gh/woolnerd/production-rag-system/branch/main/graph/badge.svg)](https://codecov.io/gh/woolnerd/production-rag-system)

A production-grade RAG (Retrieval Augmented Generation) chatbot that allows users to upload documents and ask questions with proper source citations.

## Features

- **Document Upload**: Support for PDF, DOCX, and TXT files with drag-and-drop interface
- **Contextual Chunking**: Intelligent document chunking with metadata for better retrieval
- **Hybrid Search**: Combines vector similarity (pgvector) and full-text search (PostgreSQL)
- **Reranking**: Cohere rerank-english-v3.0 for improved relevance
- **Answer Generation**: Claude 3.5 Sonnet with source citations
- **Clean UI**: Simple, responsive chat interface

## Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Database**: Supabase (PostgreSQL + pgvector)
- **Embeddings**: Google Gemini text-embedding-004 (768 dimensions)
- **Reranking**: Cohere rerank-english-v3.0
- **LLM**: Anthropic Claude 3.5 Sonnet
- **Frontend**: HTML/CSS/JavaScript

## Architecture

```
User → Document Upload → Text Extraction → Contextual Chunking → Embedding → Storage
                                                                                  ↓
User ← Answer Generation ← Claude ← Reranking ← Hybrid Search ← Query Embedding ← Query
```

### Document Processing Flow
1. Upload document (PDF/DOCX/TXT)
2. Extract text content
3. Split into semantic chunks (400-600 tokens)
4. Add contextual metadata to each chunk
5. Generate embeddings with Gemini
6. Store in Supabase with metadata

### Query/Retrieval Flow
1. User submits question
2. Generate query embedding with Gemini
3. Hybrid search:
   - Vector similarity search (top 30)
   - Full-text search (top 30)
   - Combine with RRF (Reciprocal Rank Fusion)
4. Rerank with Cohere (top 5)
5. Generate answer with Claude
6. Return answer with source citations

## Setup

### Prerequisites
- Python 3.11 or higher
- Supabase account
- API keys for:
  - Google AI (Gemini)
  - Cohere
  - Anthropic

### Local Development

1. **Clone and setup**:
```bash
git clone <repository-url>
cd rag-demo
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r backend/requirements.txt
```

2. **Configure environment variables**:
```bash
cp .env.example .env
# Edit .env with your API keys
```

3. **Set up database** (see Database Setup section)

4. **Run the application**:
```bash
cd backend
uvicorn app.main:app --reload
```

5. **Access the application**:
- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Frontend: http://localhost:8000 (serves static files)

### Database Setup

See `docs/database-setup.md` for detailed instructions on setting up Supabase with pgvector.

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test types
pytest tests/unit/
pytest tests/integration/

# Run performance tests
locust -f tests/performance/locustfile.py
```

## CI/CD

This project uses GitHub Actions for continuous integration and deployment:
- **CI**: Runs tests, linting, and coverage checks on every push/PR
- **CD**: Automated deployment to production on main branch merge

See `.github/workflows/` for pipeline configurations.

## API Documentation

### Endpoints

#### `POST /api/documents/upload`
Upload a document for processing.

**Request**: Multipart form data with file
**Response**: Document ID and processing status

#### `POST /api/query`
Ask a question about uploaded documents.

**Request**:
```json
{
  "query": "What is the main topic?",
  "document_ids": ["optional-filter"]
}
```

**Response**:
```json
{
  "answer": "The answer text...",
  "sources": [
    {
      "document": "filename.pdf",
      "content": "relevant chunk...",
      "score": 0.95
    }
  ],
  "metadata": {
    "chunks_used": 5,
    "processing_time_ms": 1234
  }
}
```

#### `GET /api/documents`
List all uploaded documents.

#### `DELETE /api/documents/{id}`
Delete a document and all its chunks.

## Deployment

See `docs/deployment.md` for production deployment instructions.

## Performance Considerations

- **Rate Limits**: Configurable limits for uploads and queries
- **File Size**: Default max 10MB per document
- **Response Time**: ~2-3 seconds for typical queries (p95)
- **Concurrent Users**: Tested with 50 simultaneous queries

## Limitations

- Scanned PDFs (images) are not supported
- Very large documents (>1000 pages) may take several minutes to process
- API costs scale with usage (see cost estimates in docs)

## Contributing

See `CONTRIBUTING.md` for guidelines.

## License

MIT License - see `LICENSE` file for details.

## Support

For issues and questions, please open a GitHub issue.

---

**Built with Claude Code** 🤖
