"""
SWS CSRF nonce management — H-2.
"""
import secrets


class CsrfManager:
    """Per-instance CSRF nonce, generated on shell start, never persisted."""

    def __init__(self):
        self._nonce = secrets.token_hex(32)

    @property
    def nonce(self) -> str:
        return self._nonce

    def validate(self, nonce: str) -> bool:
        if not nonce:
            return False
        return secrets.compare_digest(self._nonce, nonce)

    def regenerate(self):
        self._nonce = secrets.token_hex(32)


# Module-level singleton
_csrf = CsrfManager()


def get_csrf() -> CsrfManager:
    return _csrf