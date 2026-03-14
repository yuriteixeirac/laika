from hashlib import sha256


def compute_hash(content: str) -> str:
    """Computes a sha256 hash of a file's content"""
    return sha256(
        data=content.encode()
    ).hexdigest()
