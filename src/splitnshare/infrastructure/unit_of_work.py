"""Implement atomic application transactions with asynchronous SQLAlchemy sessions."""

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from splitnshare.application.ports import UnitOfWork, UnitOfWorkFactory
from splitnshare.infrastructure.repositories import (
    SqlAlchemyActivityRepository,
    SqlAlchemyExpenseRepository,
    SqlAlchemyFriendRepository,
    SqlAlchemyGuestRepository,
    SqlAlchemySettlementRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyUserSettingsRepository,
)


class SqlAlchemyUnitOfWork(UnitOfWork):
    """Expose repositories sharing one asynchronous database session."""

    users: SqlAlchemyUserRepository
    user_settings: SqlAlchemyUserSettingsRepository
    guests: SqlAlchemyGuestRepository
    expenses: SqlAlchemyExpenseRepository
    friends: SqlAlchemyFriendRepository
    settlements: SqlAlchemySettlementRepository
    activities: SqlAlchemyActivityRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Store the session factory used when entering the transaction scope."""
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        """Open a session and bind all repositories to it."""
        self._session = self._session_factory()
        self.users = SqlAlchemyUserRepository(self._session)
        self.user_settings = SqlAlchemyUserSettingsRepository(self._session)
        self.guests = SqlAlchemyGuestRepository(self._session)
        self.expenses = SqlAlchemyExpenseRepository(self._session)
        self.friends = SqlAlchemyFriendRepository(self._session)
        self.settlements = SqlAlchemySettlementRepository(self._session)
        self.activities = SqlAlchemyActivityRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Roll back failed work when necessary and always close the session."""
        assert self._session is not None
        if exc_type is not None:
            await self._session.rollback()
        await self._session.close()

    async def commit(self) -> None:
        """Commit all changes accumulated in the shared session."""
        assert self._session is not None
        await self._session.commit()


class SqlAlchemyUnitOfWorkFactory(UnitOfWorkFactory):
    """Create SQLAlchemy units of work from a configured session factory."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Store the session factory shared by produced units of work."""
        self._session_factory = session_factory

    def __call__(self) -> UnitOfWork:
        """Return a new unopened unit of work."""
        return SqlAlchemyUnitOfWork(self._session_factory)
