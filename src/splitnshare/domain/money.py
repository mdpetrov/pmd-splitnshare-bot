"""Represent and parse monetary values without floating-point arithmetic."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext

from splitnshare.domain.currencies import CURRENCY_EXPONENTS, normalize_currency
from splitnshare.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class Money:
    """Store a non-negative monetary amount in integer minor units."""
    minor: int
    currency: str

    def __post_init__(self) -> None:
        """Normalize and validate the currency and amount."""
        currency = normalize_currency(self.currency)
        if self.minor < 0:
            raise ValidationError("Amount cannot be negative.")
        object.__setattr__(self, "currency", currency)

    @classmethod
    def parse(cls, value: str, currency: str) -> "Money":
        """Parse a decimal amount according to the currency's exponent."""
        code = normalize_currency(currency)
        exponent = CURRENCY_EXPONENTS[code]
        try:
            decimal = Decimal(value.strip())
        except InvalidOperation as exc:
            raise ValidationError("Enter a valid amount.") from exc
        if not decimal.is_finite() or decimal <= 0:
            raise ValidationError("Amount must be greater than zero.")
        # Reject values outside the database range before scaling or converting to int.
        if decimal > Decimal(2**63 - 1).scaleb(-exponent):
            raise ValidationError("Amount is too large.")
        with localcontext() as context:
            context.prec = 28
            quantum = Decimal((0, (1,), -exponent))
            if decimal.quantize(quantum) != decimal:
                raise ValidationError(f"{code} supports at most {exponent} decimal places.")
            return cls(int(decimal.scaleb(exponent)), code)

    def format(self) -> str:
        """Format the amount for display with its ISO currency code."""
        exponent = CURRENCY_EXPONENTS[self.currency]
        value = Decimal(self.minor).scaleb(-exponent)
        return f"{value:.{exponent}f} {self.currency}"
