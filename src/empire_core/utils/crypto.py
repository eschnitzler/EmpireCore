import hashlib


def hash_password(password: str) -> str:
    """
    Hashes the password using MD5, which is the standard for this SFS implementation.
    """
    return hashlib.md5(password.encode("utf-8")).hexdigest()
