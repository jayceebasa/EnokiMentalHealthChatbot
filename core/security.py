import os
from typing import Optional

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # cryptography not installed yet
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore

_fernet: Optional[Fernet] = None


def _init_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    key = os.getenv("ENCRYPTION_KEY")
    if not key or not Fernet:
        _fernet = None
    else:
        try:
            _fernet = Fernet(key.encode() if not key.startswith("gAAAA") else key)
        except Exception:
            _fernet = None
    return _fernet


def encrypt_value(plaintext: str) -> str:
    f = _init_fernet()
    if not f or not plaintext:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(token: str) -> str:
    f = _init_fernet()
    if not f or not token:
        return token
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken:
        return token  # assume it was plaintext
    except Exception:
        return token


def is_encrypted(value: str) -> bool:
    f = _init_fernet()
    if not f or not value:
        return False
    # Fernet tokens are URL-safe base64 strings that start with 'gAAAA'
    if not value.startswith('gAAAA'):
        return False
    try:
        f.decrypt(value.encode())
        return True
    except Exception:
        return False
