"""Encode UUIDs compactly enough for Telegram's callback-data limit."""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from uuid import UUID


def uuid_token(value: UUID | str) -> str:
    """Encode a UUID as a 22-character URL-safe token without padding."""
    parsed = value if isinstance(value, UUID) else UUID(value)
    return urlsafe_b64encode(parsed.bytes).decode("ascii").rstrip("=")


def uuid_from_token(token: str) -> UUID:
    """Decode a URL-safe UUID token or raise ``ValueError`` when malformed."""
    try:
        decoded = urlsafe_b64decode(token + "=" * (-len(token) % 4))
        if len(decoded) != 16:
            raise ValueError("A UUID token must decode to 16 bytes.")
        return UUID(bytes=decoded)
    except (Base64Error, UnicodeEncodeError) as exc:
        raise ValueError("Invalid UUID token.") from exc
