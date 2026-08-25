from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from splitnshare.domain.errors import ValidationError

_EXPONENTS = {"BHD": 3, "IQD": 3, "JOD": 3, "JPY": 0, "KWD": 3, "OMR": 3}


@dataclass(frozen=True, slots=True)
class Money:
    minor: int
    currency: str

    def __post_init__(self) -> None:
        currency = self.currency.upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValidationError("Currency must be a three-letter ISO code.")
        if self.minor < 0:
            raise ValidationError("Amount cannot be negative.")
        object.__setattr__(self, "currency", currency)

    @classmethod
    def parse(cls, value: str, currency: str) -> "Money":
        code = currency.strip().upper()
        exponent = _EXPONENTS.get(code, 2)
        quantum = Decimal(1).scaleb(-exponent)
        try:
            decimal = Decimal(value.strip())
        except InvalidOperation as exc:
            raise ValidationError("Enter a valid amount.") from exc
        if not decimal.is_finite() or decimal <= 0:
            raise ValidationError("Amount must be greater than zero.")
        if decimal.quantize(quantum, rounding=ROUND_HALF_UP) != decimal:
            raise ValidationError(f"{code} supports at most {exponent} decimal places.")
        return cls(int(decimal.scaleb(exponent)), code)

    def format(self) -> str:
        exponent = _EXPONENTS.get(self.currency, 2)
        value = Decimal(self.minor).scaleb(-exponent)
        return f"{value:.{exponent}f} {self.currency}"

