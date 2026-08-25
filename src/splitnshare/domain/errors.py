class DomainError(ValueError):
    """Base error safe to show to a user."""


class ValidationError(DomainError):
    pass


class NotFoundError(DomainError):
    pass


class PermissionDeniedError(DomainError):
    pass


class ConflictError(DomainError):
    pass

