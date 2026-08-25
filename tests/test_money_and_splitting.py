from uuid import UUID

import pytest

from splitnshare.domain.errors import ValidationError
from splitnshare.domain.money import Money
from splitnshare.domain.splitting import EqualSplitStrategy, ExactSplitStrategy

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


def test_equal_split_distributes_remainder_by_position() -> None:
    allocations = EqualSplitStrategy().allocate(1000, [P1, P2, P3])
    assert [allocation.owed_minor for allocation in allocations] == [334, 333, 333]


def test_exact_split_must_reconcile() -> None:
    with pytest.raises(ValidationError):
        ExactSplitStrategy().allocate(1000, [P1, P2], {P1: 500, P2: 499}, P1)

