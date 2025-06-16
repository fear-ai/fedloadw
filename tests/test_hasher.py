import hashlib
import pytest
from hasher import hash_content

def test_hash_content_basic():
    """Test basic hashing functionality."""
    content = "Hello, World!"
    expected_md5 = hashlib.md5(content.encode('utf-8')).hexdigest()
    assert hash_content(content, algorithm="md5") == expected_md5

def test_hash_content_invalid_algorithm():
    """Test handling of invalid algorithm."""
    content = "Hello, World!"
    with pytest.raises(ValueError):
        hash_content(content, algorithm="invalid_algorithm")

def test_hash_content_size_limit():
    """Test content size limit functionality."""
    content = "A" * 1000  # 1000 bytes
    max_size_mb = 1  # 1 KB
    result = hash_content(content, max_size_mb=max_size_mb)
    expected = hashlib.md5(content.encode('utf-8')[:1024]).hexdigest()
    assert result == expected

def test_hash_content_initial_bytes():
    """Test initial bytes functionality."""
    content = "Hello, World!"
    initial_bytes = 5
    result = hash_content(content, initial_bytes=initial_bytes)
    expected = hashlib.md5(content.encode('utf-8')[:initial_bytes]).hexdigest()
    assert result == expected

def test_hash_content_type_error():
    """Test type error handling."""
    content = 123  # Not a string
    with pytest.raises(TypeError):
        hash_content(content)

def test_hash_content_empty_string():
    """Test hashing of empty string."""
    content = ""
    expected_md5 = hashlib.md5(content.encode('utf-8')).hexdigest()
    assert hash_content(content) == expected_md5

def test_hash_content_unicode():
    """Test hashing of unicode content."""
    content = "Hello, 世界!"
    expected_md5 = hashlib.md5(content.encode('utf-8')).hexdigest()
    assert hash_content(content) == expected_md5

def test_hash_content_large():
    """Test hashing of large content."""
    content = "A" * 1000000  # 1MB
    result = hash_content(content)
    assert len(result) == 32  # MD5 hash length

def test_hash_content_size_warning():
    """Test content size warning and truncation."""
    content = "A" * 2000000  # 2MB
    max_size_mb = 1  # 1MB
    result = hash_content(content, max_size_mb=max_size_mb)
    expected = hashlib.md5(content.encode('utf-8')[:1024 * 1024]).hexdigest()
    assert result == expected

def test_hash_content_sha1():
    """Test SHA1 algorithm."""
    content = "Hello, World!"
    expected_sha1 = hashlib.sha1(content.encode('utf-8')).hexdigest()
    assert hash_content(content, algorithm="sha1") == expected_sha1

def test_hash_content_sha256():
    """Test SHA256 algorithm."""
    content = "Hello, World!"
    expected_sha256 = hashlib.sha256(content.encode('utf-8')).hexdigest()
    assert hash_content(content, algorithm="sha256") == expected_sha256 