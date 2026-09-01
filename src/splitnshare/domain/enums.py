from enum import StrEnum


class PersonKind(StrEnum):
    USER = "user"
    GUEST = "guest"


class GuestCreationMethod(StrEnum):
    TELEGRAM = "telegram"
    MANUAL = "manual"


class GuestTransferStatus(StrEnum):
    ACTIVE = "active"
    TRANSFERRED = "transferred"


class GroupStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class GroupRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class SplitMethod(StrEnum):
    EQUAL = "equal"
    EXACT = "exact"


class TransferStatus(StrEnum):
    COMPLETED = "completed"


class Language(StrEnum):
    ENGLISH = "en"
    RUSSIAN = "ru"


class FriendSource(StrEnum):
    DIRECT = "direct"
    EXPENSE = "expense"
