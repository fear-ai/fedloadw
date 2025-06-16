import hashlib
import logging

logger = logging.getLogger(__name__)

def hash_content(content, algorithm="md5", initial_bytes=None, max_size_mb=2):
    """
    Hash content with configurable algorithm and optimizations.

    Args:
        content (str): Content to hash
        algorithm (str): Hash algorithm ('md5', 'sha256', 'sha1')
        initial_bytes (int): If specified, only hash first N bytes for quick change detection
        max_size_mb (int): Maximum content size in MB before truncation (default: 2MB)

    Returns:
        str: Hexadecimal hash digest

    Raises:
        TypeError: If content is not a string
        ValueError: If algorithm is not supported
    """
    if not isinstance(content, str):
        raise TypeError("Content must be a string")

    # Convert content to bytes
    content_bytes = content.encode('utf-8')
    content_length = len(content_bytes)

    # Check content size limit
    if max_size_mb:
        max_bytes = max_size_mb * 1024 * 1024
        if content_length > max_bytes:
            logger.warning(f"Content size ({content_length} bytes) exceeds limit ({max_bytes} bytes), truncating")
            content_bytes = content_bytes[:max_bytes]
            content_length = max_bytes

    # Use initial bytes for quick change detection if specified
    if initial_bytes and content_length > initial_bytes:
        logger.debug(f"Using initial {initial_bytes} bytes for quick hash")
        content_bytes = content_bytes[:initial_bytes]
        content_length = initial_bytes

    # Select hash algorithm
    if algorithm == "md5":
        hasher = hashlib.md5()
    elif algorithm == "sha256":
        hasher = hashlib.sha256()
    elif algorithm == "sha1":
        hasher = hashlib.sha1()
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")

    hasher.update(content_bytes)
    return hasher.hexdigest()
