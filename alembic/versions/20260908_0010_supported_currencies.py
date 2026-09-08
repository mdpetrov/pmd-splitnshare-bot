"""Validate supported currencies and correct legacy minor-unit scales.

Revision ID: 20260908_0010
Revises: 20260907_0009

The registry is frozen here so future supported-currency changes cannot alter
this migration. Stop the bot while upgrading or downgrading. No rounding or
automatic currency substitution is permitted.
"""

import sqlalchemy as sa

from alembic import context, op

revision = "20260908_0010"
down_revision = "20260907_0009"
branch_labels = None
depends_on = None

# SIX List One (2026-01-01), verified 2026-09-08; matches the initial registry.
_SUPPORTED = frozenset(
    "AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND "
    "BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUP CVE "
    "CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD "
    "GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY "
    "KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD "
    "MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO "
    "NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF "
    "SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB "
    "TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VED VES VND "
    "VUV WST XAD XAF XCD XCG XOF XPF YER ZAR ZMW ZWG "
    .split()
)
# All these currencies previously used the two-decimal fallback.
_CHANGED_EXPONENTS = {
    "BIF": 0,
    "CLP": 0,
    "DJF": 0,
    "GNF": 0,
    "ISK": 0,
    "KMF": 0,
    "KRW": 0,
    "LYD": 3,
    "PYG": 0,
    "RWF": 0,
    "TND": 3,
    "UGX": 0,
    "VND": 0,
    "VUV": 0,
    "XAF": 0,
    "XOF": 0,
    "XPF": 0,
}
_MAX_MINOR = 2**63 - 1


def _amount_columns() -> list[tuple]:
    """Describe stored amounts and their currency, including expense shares."""
    expenses = sa.table(
        "expenses", sa.column("id"), sa.column("currency"), sa.column("total_minor")
    )
    splits = sa.table(
        "expense_splits", sa.column("expense_id"), sa.column("owed_minor")
    )
    split_currency = (
        sa.select(expenses.c.currency)
        .where(expenses.c.id == splits.c.expense_id)
        .scalar_subquery()
    )
    columns = [
        (expenses, expenses.c.total_minor, expenses.c.currency),
        (splits, splits.c.owed_minor, split_currency),
    ]
    for name in ("debts", "settlements"):
        table = sa.table(name, sa.column("currency"), sa.column("amount_minor"))
        columns.append((table, table.c.amount_minor, table.c.currency))
    return columns


def _rescale(*, reverse: bool) -> None:
    """Preflight every amount, then change scales without changing face values."""
    if context.is_offline_mode():
        raise RuntimeError("Currency migration requires an online data validation.")
    connection = op.get_bind()
    columns = _amount_columns()
    settings = sa.table("user_settings", sa.column("default_currency"))
    currency_columns = [(table, currency) for table, _, currency in columns]
    currency_columns.append((settings, settings.c.default_currency))
    if not reverse:
        for table, currency in currency_columns:
            unsupported = connection.execute(
                sa.select(currency).select_from(table)
                .where(currency.not_in(sorted(_SUPPORTED))).distinct()
            ).scalars().all()
            if unsupported:
                raise RuntimeError(
                    f"Unsupported currencies in {table.name}: {unsupported}. "
                    "Review legacy data before retrying; no currency is substituted."
                )

    # Validate every table first: even a fractional share prevents the whole upgrade.
    for code, exponent in _CHANGED_EXPONENTS.items():
        difference = (2 - exponent) if reverse else (exponent - 2)
        factor = 10 ** abs(difference)
        for table, amount, currency in columns:
            invalid = amount % factor != 0 if difference < 0 else amount > _MAX_MINOR // factor
            found = connection.scalar(
                sa.select(sa.func.count()).select_from(table)
                .where(currency == code, invalid)
            )
            if found:
                raise RuntimeError(
                    f"Cannot rescale {table.name} amounts for {code}: "
                    "rounding or overflow would be required. "
                    "Review legacy amounts before retrying; no amounts were changed."
                )

    for code, exponent in _CHANGED_EXPONENTS.items():
        difference = (2 - exponent) if reverse else (exponent - 2)
        factor = 10 ** abs(difference)
        for table, amount, currency in columns:
            scaled = (
                sa.cast(amount.op("/")(factor), sa.BigInteger)
                if difference < 0 else amount * factor
            )
            connection.execute(
                table.update().where(currency == code).values({amount.name: scaled})
            )


def upgrade() -> None:
    """Reject incompatible legacy data and preserve amounts using ISO precision."""
    _rescale(reverse=False)


def downgrade() -> None:
    """Restore legacy scales only when every amount can be represented exactly."""
    _rescale(reverse=True)

