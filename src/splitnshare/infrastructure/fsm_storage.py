"""Persist aiogram sessions and recoverable expense drafts in the application database."""

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from splitnshare.domain.errors import NotFoundError
from splitnshare.infrastructure.models import ConversationStateModel, ExpenseDraftModel


def conversation_key(key: StorageKey) -> str:
    """Encode every aiogram scope component without separator collisions."""
    return json.dumps([
        key.bot_id, key.chat_id, key.user_id, key.thread_id,
        key.business_connection_id, key.destiny,
    ], separators=(",", ":"))


@dataclass(frozen=True)
class SavedExpenseDraft:
    """Expose a detached, owner-scoped snapshot for draft navigation."""

    id: UUID
    state: str
    data: dict[str, Any]


class SqlAlchemyFSMStorage(BaseStorage):
    """Durably store each FSM change and checkpoint unfinished expenses."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Reuse the bot's existing database connection pool."""
        self._session_factory = session_factory

    async def _row(self, session: AsyncSession, key: StorageKey) -> ConversationStateModel:
        """Lock or initialize one conversation inside the caller's transaction."""
        identifier = conversation_key(key)
        row = await session.get(ConversationStateModel, identifier, with_for_update=True)
        if row is None:
            row = ConversationStateModel(
                key=identifier, telegram_user_id=key.user_id, data={}, state=None,
            )
            session.add(row)
            await session.flush()
        return row

    async def _checkpoint(self, session: AsyncSession, row: ConversationStateModel) -> None:
        """Refresh the active expense snapshot without touching saved ledger entries."""
        if not row.state or not row.state.startswith("AddExpenseStates:"):
            return
        identifier = row.data.get("draft_id")
        if not identifier:
            return
        draft_id = UUID(str(identifier))
        draft = await session.get(ExpenseDraftModel, draft_id)
        if draft is None:
            session.add(ExpenseDraftModel(
                id=draft_id, conversation_key=row.key, state=row.state, data=deepcopy(row.data),
            ))
        elif draft.conversation_key == row.key:
            draft.state = row.state
            draft.data = deepcopy(row.data)
        else:
            raise NotFoundError("Draft not found.")

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        """Persist the current step, leaving expense checkpoints available after clear."""
        async with self._session_factory.begin() as session:
            if state is None:
                existing = await session.get(ConversationStateModel, conversation_key(key))
                if existing is None:
                    return
            row = await self._row(session, key)
            row.state = state.state if isinstance(state, State) else state
            await self._checkpoint(session, row)

    async def get_state(self, key: StorageKey) -> str | None:
        """Load the last committed step after any bot restart."""
        async with self._session_factory() as session:
            row = await session.get(ConversationStateModel, conversation_key(key))
            return row.state if row else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        """Replace entered values and update the expense snapshot in one transaction."""
        async with self._session_factory.begin() as session:
            if not data:
                existing = await session.get(ConversationStateModel, conversation_key(key))
                if existing is None:
                    return
            row = await self._row(session, key)
            row.data = deepcopy(dict(data))
            await self._checkpoint(session, row)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        """Return detached entered values without sharing mutable session objects."""
        async with self._session_factory() as session:
            row = await session.get(ConversationStateModel, conversation_key(key))
            return deepcopy(row.data) if row else {}

    async def update_data(self, key: StorageKey, data: Mapping[str, Any]) -> dict[str, Any]:
        """Merge values under the conversation lock and checkpoint the result."""
        async with self._session_factory.begin() as session:
            row = await self._row(session, key)
            row.data = {**row.data, **deepcopy(dict(data))}
            await self._checkpoint(session, row)
            return deepcopy(row.data)

    async def list_drafts(self, key: StorageKey, offset: int = 0) -> tuple[SavedExpenseDraft, ...]:
        """Return eleven snapshots so the UI can show ten and detect a next page."""
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(ExpenseDraftModel)
                .where(ExpenseDraftModel.conversation_key == conversation_key(key))
                .order_by(ExpenseDraftModel.updated_at.desc(), ExpenseDraftModel.id.desc())
                .offset(max(0, offset)).limit(11)
            )
            return tuple(SavedExpenseDraft(row.id, row.state, deepcopy(row.data)) for row in rows)

    async def resume(self, key: StorageKey, draft_id: UUID) -> SavedExpenseDraft:
        """Activate an owned snapshot while preserving the previously active expense."""
        async with self._session_factory.begin() as session:
            row = await self._row(session, key)
            draft = await session.get(ExpenseDraftModel, draft_id, with_for_update=True)
            if draft is None or draft.conversation_key != row.key:
                raise NotFoundError("Draft not found.")
            row.state = draft.state
            row.data = deepcopy(draft.data)
            return SavedExpenseDraft(draft.id, draft.state, deepcopy(draft.data))

    async def discard(self, key: StorageKey, draft_id: UUID) -> None:
        """Explicitly remove one owned draft and clear it if currently active."""
        async with self._session_factory.begin() as session:
            row = await self._row(session, key)
            draft = await session.get(ExpenseDraftModel, draft_id, with_for_update=True)
            if draft is None or draft.conversation_key != row.key:
                raise NotFoundError("Draft not found.")
            if row.data.get("draft_id") == str(draft_id):
                row.state, row.data = None, {}
            await session.delete(draft)

    async def close(self) -> None:
        """Leave disposal of the shared database engine to application shutdown."""
