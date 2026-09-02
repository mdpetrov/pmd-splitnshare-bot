"""Provide the production database connectivity smoke-test command."""

import asyncio
import os

from sqlalchemy import text

from splitnshare.infrastructure.database import create_engine


async def check_database(database_url: str) -> None:
    """Open a connection and verify that PostgreSQL answers a trivial query."""
    engine = create_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.scalar(text("SELECT 1"))
            if result != 1:
                raise RuntimeError("PostgreSQL returned an unexpected health-check result.")
    finally:
        await engine.dispose()


def main() -> None:
    """Run the database smoke test using environment configuration."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set.")

    asyncio.run(check_database(database_url))
    print("PostgreSQL application smoke test: OK")


if __name__ == "__main__":
    main()
