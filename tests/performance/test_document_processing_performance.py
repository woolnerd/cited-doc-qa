"""Performance benchmarks for document processing."""

from unittest.mock import patch

import pytest
from app.services.chunking import chunk_text
from app.services.document_processor import DocumentProcessor
from app.services.text_extraction import TextExtractor

pytestmark = pytest.mark.benchmark


@pytest.fixture
def document_processor():
    """Create document processor instance."""
    return DocumentProcessor()


@pytest.fixture
def text_extractor():
    """Create text extractor instance."""
    return TextExtractor()


def test_text_extraction_small(benchmark, text_extractor, sample_text_small):
    """Benchmark text extraction for small documents (1 page)."""
    sample_text_small.seek(0)
    result = benchmark(text_extractor.extract_from_txt, sample_text_small)
    assert len(result) > 0


def test_text_extraction_medium(benchmark, text_extractor, sample_text_medium):
    """Benchmark text extraction for medium documents (10 pages)."""
    sample_text_medium.seek(0)
    result = benchmark(text_extractor.extract_from_txt, sample_text_medium)
    assert len(result) > 0


def test_text_extraction_large(benchmark, text_extractor, sample_text_large):
    """Benchmark text extraction for large documents (50 pages)."""
    sample_text_large.seek(0)
    result = benchmark(text_extractor.extract_from_txt, sample_text_large)
    assert len(result) > 0


def test_pdf_extraction_small(benchmark, text_extractor, sample_pdf_small):
    """Benchmark PDF extraction for small PDFs (1 page)."""
    sample_pdf_small.seek(0)
    result = benchmark(text_extractor.extract_from_pdf, sample_pdf_small)
    assert len(result) > 0


def test_pdf_extraction_medium(benchmark, text_extractor, sample_pdf_medium):
    """Benchmark PDF extraction for medium PDFs (10 pages)."""
    sample_pdf_medium.seek(0)
    result = benchmark(text_extractor.extract_from_pdf, sample_pdf_medium)
    assert len(result) > 0


def test_pdf_extraction_large(benchmark, text_extractor, sample_pdf_large):
    """Benchmark PDF extraction for large PDFs (50 pages)."""
    sample_pdf_large.seek(0)
    result = benchmark(text_extractor.extract_from_pdf, sample_pdf_large)
    assert len(result) > 0


def test_chunking_small_text(benchmark):
    """Benchmark text chunking for small documents."""
    text = "Python programming. " * 100
    result = benchmark(chunk_text, text)
    assert len(result) > 0


def test_chunking_medium_text(benchmark):
    """Benchmark text chunking for medium documents."""
    text = "Software engineering best practices. " * 1000
    result = benchmark(chunk_text, text)
    assert len(result) > 0


def test_chunking_large_text(benchmark):
    """Benchmark text chunking for large documents."""
    text = "Enterprise software development. " * 5000
    result = benchmark(chunk_text, text)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_document_processing_end_to_end_small(
    benchmark, document_processor, sample_text_small
):
    """Benchmark end-to-end document processing for small documents."""
    with (
        patch(
            "app.services.embeddings.EmbeddingService.generate_embedding"
        ) as mock_embed,
        patch(
            "app.services.document_processor.DocumentProcessor._store_chunks"
        ) as mock_store,
    ):
        mock_embed.return_value = [0.1] * 768
        mock_store.return_value = None

        sample_text_small.seek(0)

        async def process():
            await document_processor.process_document(
                document_id="bench-doc-1",
                file_content=sample_text_small.read(),
                filename="test.txt",
            )

        await benchmark.pedantic(process, rounds=10, iterations=1)


@pytest.mark.asyncio
async def test_document_processing_end_to_end_medium(
    benchmark, document_processor, sample_text_medium
):
    """Benchmark end-to-end document processing for medium documents."""
    with (
        patch(
            "app.services.embeddings.EmbeddingService.generate_embedding"
        ) as mock_embed,
        patch(
            "app.services.document_processor.DocumentProcessor._store_chunks"
        ) as mock_store,
    ):
        mock_embed.return_value = [0.1] * 768
        mock_store.return_value = None

        sample_text_medium.seek(0)

        async def process():
            await document_processor.process_document(
                document_id="bench-doc-2",
                file_content=sample_text_medium.read(),
                filename="test.txt",
            )

        await benchmark.pedantic(process, rounds=5, iterations=1)
