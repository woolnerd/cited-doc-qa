"""Performance test configuration and fixtures."""

from io import BytesIO

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


@pytest.fixture
def sample_text_small():
    """Small text document (1 page, ~500 words)."""
    text = "Python programming is a powerful tool. " * 100
    return BytesIO(text.encode())


@pytest.fixture
def sample_text_medium():
    """Medium text document (10 pages, ~5000 words)."""
    text = "This is a comprehensive document about software engineering. " * 1000
    return BytesIO(text.encode())


@pytest.fixture
def sample_text_large():
    """Large text document (50 pages, ~25000 words)."""
    text = "Enterprise software development requires careful planning. " * 5000
    return BytesIO(text.encode())


@pytest.fixture
def sample_pdf_small():
    """Small PDF document (1 page)."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(100, 750, "This is a test PDF document.")
    for i in range(50):
        c.drawString(100, 700 - i * 12, f"Line {i}: Sample content for testing.")
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


@pytest.fixture
def sample_pdf_medium():
    """Medium PDF document (10 pages)."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    for page in range(10):
        c.drawString(100, 750, f"Page {page + 1}")
        for i in range(50):
            c.drawString(100, 700 - i * 12, f"Line {i}: Content for page {page + 1}.")
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


@pytest.fixture
def sample_pdf_large():
    """Large PDF document (50 pages)."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    for page in range(50):
        c.drawString(100, 750, f"Page {page + 1}")
        for i in range(50):
            c.drawString(100, 700 - i * 12, f"Line {i}: Content for page {page + 1}.")
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer
