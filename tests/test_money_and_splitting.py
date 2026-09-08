from uuid import UUID

import pytest

from splitnshare.config import Settings
from splitnshare.domain.errors import ValidationError
from splitnshare.domain.money import Money
from splitnshare.domain.splitting import EqualSplitStrategy, ExactSplitStrategy
from splitnshare.presentation.helpers import parse_share_minor, parse_total

P1 = UUID("00000000-0000-0000-0000-000000000001")
P2 = UUID("00000000-0000-0000-0000-000000000002")
P3 = UUID("00000000-0000-0000-0000-000000000003")


def test_money_uses_currency_minor_units() -> None:
    assert Money.parse("12.34", "USD").minor == 1234
    assert Money.parse("123", "JPY").minor == 123
    assert Money.parse("1.234", "KWD").minor == 1234


def test_money_rejects_excess_precision() -> None:
    with pytest.raises(ValidationError):
        Money.parse("1.001", "USD")


@pytest.mark.parametrize("code", ["KRW", "VND", "CLP", "ISK", "XAF", "XOF", "XPF"])
def test_zero_decimal_currencies_use_whole_units(code: str) -> None:
    assert Money.parse("123", code) == Money(123, code)
    assert Money(123, code).format() == f"123 {code}"
    with pytest.raises(ValidationError, match="0 decimal places"):
        Money.parse("123.01", code)


@pytest.mark.parametrize("code", ["LYD", "TND", "BHD", "IQD", "JOD", "KWD", "OMR"])
def test_three_decimal_currencies_preserve_smallest_unit(code: str) -> None:
    assert Money.parse("1.234", code) == Money(1234, code)
    assert Money(1234, code).format() == f"1.234 {code}"
    with pytest.raises(ValidationError, match="3 decimal places"):
        Money.parse("1.2345", code)


@pytest.mark.parametrize("code", ["ZZZ", "BTC", "XAU", "XXX", "XTS", "CLF", "BGN", "АБВ"])
def test_unsupported_codes_are_rejected_in_every_money_entry_point(code: str) -> None:
    with pytest.raises(ValidationError, match="Unsupported currency"):
        Money(123, code)
    with pytest.raises(ValidationError, match="Unsupported currency"):
        Money.parse("1", code)
    with pytest.raises(ValidationError):
        parse_total(f"1 {code}", "USD")
    with pytest.raises(ValidationError):
        parse_total("1", code)


def test_currency_normalization_and_share_precision() -> None:
    assert Money(1234, " eur ") == Money.parse("12.3400", "EUR")
    assert parse_total("1.234 tnd", "USD") == Money(1234, "TND")
    assert parse_share_minor("0", Money(100, "KRW")) == 0
    assert parse_share_minor("0.001", Money(100, "TND")) == 1
    with pytest.raises(ValidationError):
        parse_share_minor("0.01", Money(100, "KRW"))


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e100", "1e-1000",
                                       "1.00000000000000000000000000001"])
def test_invalid_or_unrepresentable_amounts_raise_domain_errors(value: str) -> None:
    with pytest.raises(ValidationError):
        Money.parse(value, "USD")


def test_runtime_default_currency_uses_the_same_registry() -> None:
    assert Settings(bot_token="test-token", default_currency=" tnd ").default_currency == "TND"
    with pytest.raises(ValueError, match="Unsupported currency"):
        Settings(bot_token="test-token", default_currency="ZZZ")


def test_equal_split_distributes_remainder_by_position() -> None:
    allocations = EqualSplitStrategy().allocate(1000, [P1, P2, P3])
    assert [allocation.owed_minor for allocation in allocations] == [334, 333, 333]


def test_exact_split_must_reconcile() -> None:
    with pytest.raises(ValidationError):
        ExactSplitStrategy().allocate(1000, [P1, P2], {P1: 500, P2: 499}, P1)

