"""Domain-specific exceptions safe to translate into user-facing errors."""

class DomainError(ValueError):
    """Base class for expected business-rule failures."""
    """Base error safe to show to a user."""


class ValidationError(DomainError):
    """Indicate that supplied data violates a validation rule."""
    pass


class NotFoundError(DomainError):
    """Indicate that a requested domain object does not exist."""
    pass


class PermissionDeniedError(DomainError):
    """Indicate that the actor is not authorized to perform an operation."""
    pass


class ConflictError(DomainError):
    """Indicate that current state conflicts with the requested operation."""
    pass
