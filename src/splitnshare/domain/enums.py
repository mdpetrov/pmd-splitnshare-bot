"""Enumerations shared by the Splitnshare domain and persistence layers."""

from enum import StrEnum


class PersonKind(StrEnum):
    """Distinguish registered users from owner-managed guests."""
    USER = "user"
    GUEST = "guest"


class GuestCreationMethod(StrEnum):
    """Record how a guest identity was originally created."""
    TELEGRAM = "telegram"
    MANUAL = "manual"


class GuestTransferStatus(StrEnum):
    """Describe whether a guest remains active or has been transferred."""
    ACTIVE = "active"
    TRANSFERRED = "transferred"


class GroupStatus(StrEnum):
    """Describe the lifecycle state of an expense group."""
    ACTIVE = "active"
    ARCHIVED = "archived"


class GroupRole(StrEnum):
    """Define a participant's permissions within a group."""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class MembershipStatus(StrEnum):
    """Describe whether a group membership is currently usable."""
    ACTIVE = "active"
    INACTIVE = "inactive"


class SplitMethod(StrEnum):
    """List the supported methods for allocating an expense."""
    EQUAL = "equal"
    EXACT = "exact"


class TransferStatus(StrEnum):
    """Describe the audit status of a guest-transfer operation."""
    COMPLETED = "completed"


class Language(StrEnum):
    """List interface languages for which translation catalogs exist."""
    ENGLISH = "en"
    RUSSIAN = "ru"


# Russian remains fully translated and database-compatible, but is intentionally
# absent from this tuple until it is ready to be offered to users again.
SELECTABLE_LANGUAGES: tuple[Language, ...] = (Language.ENGLISH,)


class FriendSource(StrEnum):
    """Record how a person entered an owner's friends list."""
    DIRECT = "direct"
    EXPENSE = "expense"
