import os
import sys
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from main import app
from fetcher import fetch_page, extract_text
from hasher import hash_content
from diff import is_changed

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)

def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data

def test_process_url_invalid(client):
    """Test URL processing with invalid URL."""
    response = client.post("/process", json={"url": "invalid-url"})
    assert response.status_code == 400
    assert "Invalid URL format" in response.json()["detail"]

def test_process_url_valid(client):
    """Test URL processing with valid URL."""
    response = client.post(
        "/process",
        json={"url": "https://example.com", "extract_entities": False}
    )
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert "timestamp" in data
    assert data["entities"] is None

def test_process_url_with_entities(client):
    """Test URL processing with entity extraction."""
    response = client.post(
        "/process",
        json={"url": "https://example.com", "extract_entities": True}
    )
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert "timestamp" in data
    assert "entities" in data

def test_fetch_page_valid():
    """Test fetching a valid page."""
    content = fetch_page("https://example.com")
    assert isinstance(content, str)
    assert len(content) > 0

def test_fetch_page_invalid():
    # Test invalid URL handling
    result = fetch_page("invalid-url")
    assert result is None, "Invalid URL should return None"

    # Test unsupported protocol
    result = fetch_page("mailto:test@example.com")
    assert result is None, "Unsupported protocol should return None"

def test_extract_text():
    """Test text extraction from HTML."""
    html = "<html><body><p>Test content</p></body></html>"
    text = extract_text(html)
    assert isinstance(text, str)
    assert "Test content" in text

def test_hash_content():
    """Test content hashing."""
    content = "Test content"
    hash_value = hash_content(content)
    assert isinstance(hash_value, str)
    assert len(hash_value) > 0

def test_is_changed():
    """Test change detection."""
    old_hash = hash_content("Old content")
    new_hash = hash_content("New content")
    assert is_changed(old_hash, new_hash)
    assert not is_changed(old_hash, old_hash)
