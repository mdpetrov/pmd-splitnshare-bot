import sqlite3
from pathlib import Path
from uuid import uuid4

from alembic.config import Config

from alembic import command


def test_friendship_migration_backfills_existing_expense_participants(
    monkeypatch,
) -> None:
    project_root = Path(__file__).parents[1]
    database_path = project_root / ".pytest_cache" / "migration-test.db"
    database_path.parent.mkdir(exist_ok=True)
    database_path.unlink(missing_ok=True)
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(project_root / "alembic.ini")

    command.upgrade(config, "20260901_0002")

    owner_id = uuid4().hex
    friend_id = uuid4().hex
    expense_id = uuid4().hex
    with sqlite3.connect(database_path) as connection:
        guest_columns_before = {
            row[1] for row in connection.execute("PRAGMA table_info(guest_profiles)")
        }
        assert "suggested_username" not in guest_columns_before
        connection.execute(
            "INSERT INTO persons (id, display_name, kind) VALUES (?, ?, ?)",
            (owner_id, "Owner", "user"),
        )
        connection.execute(
            "INSERT INTO persons (id, display_name, kind) VALUES (?, ?, ?)",
            (friend_id, "Friend", "user"),
        )
        connection.execute(
            """
            INSERT INTO user_accounts (person_id, telegram_user_id, first_name)
            VALUES (?, ?, ?)
            """,
            (owner_id, 701, "Owner"),
        )
        connection.execute(
            """
            INSERT INTO user_accounts (person_id, telegram_user_id, first_name)
            VALUES (?, ?, ?)
            """,
            (friend_id, 702, "Friend"),
        )
        connection.execute(
            """
            INSERT INTO expenses (
                id, creator_person_id, payer_person_id, description,
                total_minor, currency, split_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (expense_id, owner_id, owner_id, "Existing", 1000, "USD", "equal"),
        )
        connection.execute(
            """
            INSERT INTO expense_splits (expense_id, person_id, owed_minor, position)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            """,
            (expense_id, owner_id, 500, 0, expense_id, friend_id, 500, 1),
        )

    command.upgrade(config, "head")

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT owner_person_id, friend_person_id, source FROM friendships"
        ).fetchall()
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        guest_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(guest_profiles)")
        }

    assert rows == [(owner_id, friend_id, "expense")]
    assert revision == ("20260901_0004",)
    assert "suggested_username" in guest_columns
