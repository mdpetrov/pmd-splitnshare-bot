"""Check that adopting ISO precision preserves or explicitly rejects legacy money."""

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config

from alembic import command


@pytest.fixture
def legacy_currency_database(tmp_path, monkeypatch):
    database = tmp_path / "currencies.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database.as_posix()}")
    config = Config(Path(__file__).parents[1] / "alembic.ini")
    command.upgrade(config, "20260907_0009")
    owner, friend, expense = (uuid4().hex for _ in range(3))
    with sqlite3.connect(database) as connection:
        for person, telegram_id in ((owner, 101), (friend, 102)):
            connection.execute(
                "INSERT INTO persons (id, display_name, kind) VALUES (?, 'Person', 'user')",
                (person,),
            )
            connection.execute(
                "INSERT INTO user_accounts (person_id, telegram_user_id, first_name) "
                "VALUES (?, ?, 'Person')", (person, telegram_id),
            )
        connection.execute(
            "INSERT INTO user_settings (person_id, default_currency, language) "
            "VALUES (?, 'KRW', 'en')", (owner,),
        )
        connection.execute(
            "INSERT INTO expenses (id, creator_person_id, payer_person_id, description, "
            "total_minor, currency, split_method, deleted_at) "
            "VALUES (?, ?, ?, 'Legacy', 1000, 'KRW', 'equal', '2026-09-01')",
            (expense, owner, owner),
        )
        connection.executemany(
            "INSERT INTO expense_splits (expense_id, person_id, owed_minor, position) "
            "VALUES (?, ?, 500, ?)", [(expense, owner, 0), (expense, friend, 1)],
        )
        connection.execute(
            "INSERT INTO debts (id, expense_id, debtor_person_id, creditor_person_id, "
            "amount_minor, currency) VALUES (?, ?, ?, ?, 500, 'KRW')",
            (uuid4().hex, expense, friend, owner),
        )
        connection.execute(
            "INSERT INTO settlements (id, recorded_by_person_id, payer_person_id, "
            "recipient_person_id, amount_minor, currency, occurred_at) "
            "VALUES (?, ?, ?, ?, 200, 'KRW', '2026-09-01')",
            (uuid4().hex, owner, friend, owner),
        )
    return database, config


def _snapshot(database):
    with sqlite3.connect(database) as connection:
        return {
            table: connection.execute(f"SELECT * FROM {table}").fetchall()
            for table in ("expenses", "expense_splits", "debts", "settlements", "user_settings")
        }


@pytest.mark.parametrize(
    ("currency", "expected"), [("KRW", 10), ("TND", 10000), ("USD", 1000), ("JPY", 1000)]
)
def test_upgrade_preserves_face_values_and_downgrade_restores_storage(
    legacy_currency_database, currency, expected,
):
    database, config = legacy_currency_database
    with sqlite3.connect(database) as connection:
        for table in ("expenses", "debts", "settlements"):
            connection.execute(f"UPDATE {table} SET currency = ?", (currency,))
        connection.execute("UPDATE user_settings SET default_currency = ?", (currency,))
    before = _snapshot(database)
    command.upgrade(config, "head")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT total_minor FROM expenses").fetchone() == (expected,)
        assert connection.execute("SELECT owed_minor FROM expense_splits").fetchall() == [
            (expected // 2,), (expected // 2,),
        ]
        assert connection.execute("SELECT amount_minor FROM debts").fetchone() == (expected // 2,)
        assert connection.execute("SELECT amount_minor FROM settlements").fetchone() == (
            expected // 5,
        )
    command.downgrade(config, "20260907_0009")
    assert _snapshot(database) == before


@pytest.mark.parametrize("table", ["expenses", "debts", "settlements", "user_settings"])
def test_upgrade_rejects_unsupported_legacy_codes_without_mutation(legacy_currency_database, table):
    database, config = legacy_currency_database
    column = "default_currency" if table == "user_settings" else "currency"
    with sqlite3.connect(database) as connection:
        connection.execute(f"UPDATE {table} SET {column} = 'ZZZ'")
    before = _snapshot(database)
    with pytest.raises(RuntimeError, match="Unsupported currencies"):
        command.upgrade(config, "head")
    assert _snapshot(database) == before


@pytest.mark.parametrize(
    ("table", "column"),
    [("expenses", "total_minor"), ("expense_splits", "owed_minor"),
     ("debts", "amount_minor"), ("settlements", "amount_minor")],
)
def test_upgrade_rejects_fractional_legacy_units_without_mutation(
    legacy_currency_database, table, column,
):
    database, config = legacy_currency_database
    with sqlite3.connect(database) as connection:
        connection.execute(f"UPDATE {table} SET {column} = {column} + 1")
    before = _snapshot(database)
    with pytest.raises(RuntimeError, match="rounding or overflow"):
        command.upgrade(config, "head")
    assert _snapshot(database) == before


def test_upgrade_rejects_bigint_overflow_without_mutation(legacy_currency_database):
    database, config = legacy_currency_database
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE expenses SET currency = 'TND', total_minor = ?", (2**63 - 1,))
    before = _snapshot(database)
    with pytest.raises(RuntimeError, match="rounding or overflow"):
        command.upgrade(config, "head")
    assert _snapshot(database) == before


def test_downgrade_rejects_new_amounts_that_legacy_precision_cannot_represent(
    legacy_currency_database,
):
    database, config = legacy_currency_database
    command.upgrade(config, "head")
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE settlements SET currency = 'TND', amount_minor = 1001")
    before = _snapshot(database)
    with pytest.raises(RuntimeError, match="rounding or overflow"):
        command.downgrade(config, "20260907_0009")
    assert _snapshot(database) == before
