"""Coordinate group creation, membership, summaries, and atomic settlements."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from splitnshare.application.dto import BalanceDTO, GroupDTO, SettlementDTO
from splitnshare.application.ports import UnitOfWorkFactory
from splitnshare.domain.contexts import GroupExpenseContext
from splitnshare.domain.currencies import normalize_currency
from splitnshare.domain.errors import ConflictError, ValidationError


class GroupService:
    """Expose authorized group use cases through transaction boundaries."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        """Store the transaction factory."""
        self._uow_factory = uow_factory

    async def list_groups(self, actor_id: UUID) -> tuple[GroupDTO, ...]:
        """List groups the actor currently belongs to."""
        async with self._uow_factory() as uow:
            return tuple(await uow.groups.list_for_person(actor_id))

    async def get(self, actor_id: UUID, group_id: UUID) -> GroupDTO:
        """Read one group after checking active membership."""
        async with self._uow_factory() as uow:
            return await uow.groups.get(actor_id, group_id)

    async def create(
        self,
        actor_id: UUID,
        name: str,
        currency: str,
        members: Sequence[UUID],
    ) -> GroupDTO:
        """Validate group preferences and commit its initial membership."""
        name = " ".join(name.split())
        if not 1 <= len(name) <= 120:
            raise ValidationError("Group names must contain 1 to 120 characters.")
        currency = normalize_currency(currency)
        async with self._uow_factory() as uow:
            result = await uow.groups.create(actor_id, name, currency, members)
            await uow.commit()
            return result

    async def add_members(
        self,
        actor_id: UUID,
        group_id: UUID,
        members: Sequence[UUID],
    ) -> tuple[GroupDTO, tuple[UUID, ...]]:
        """Commit invitations and return identities requiring notification."""
        async with self._uow_factory() as uow:
            result = await uow.groups.add_members(actor_id, group_id, members)
            await uow.commit()
            return result

    async def summary(
        self,
        actor_id: UUID,
        group_id: UUID,
    ) -> tuple[GroupDTO, dict[UUID, tuple[BalanceDTO, ...]]]:
        """Calculate pairwise balances for every active group participant."""
        async with self._uow_factory() as uow:
            group = await uow.groups.get(actor_id, group_id)
            balances = {member.id: tuple(await uow.expenses.balances(
                member.id, GroupExpenseContext(group_id)
            )) for member in group.participants}
            return group, balances

    async def settle(
        self,
        actor_id: UUID,
        group_id: UUID,
        expected: Sequence[BalanceDTO],
        other_id: UUID | None = None,
    ) -> tuple[SettlementDTO, ...]:
        """Settle the reviewed balances atomically, rejecting changed or repeated requests."""
        async with self._uow_factory() as uow:
            await uow.groups.get(actor_id, group_id, for_update=True)
            context = GroupExpenseContext(group_id)
            current = tuple(balance for balance in await uow.expenses.balances(actor_id, context)
                            if other_id is None or balance.other_person_id == other_id)
            actual_values = {(b.other_person_id, b.currency): b.net_minor for b in current}
            expected_values = {(b.other_person_id, b.currency): b.net_minor for b in expected}
            if not current or actual_values != expected_values:
                raise ConflictError(
                    "Group balances changed or were already settled. Review them again."
                )
            settlements = []
            for balance in sorted(current, key=lambda b: (b.other_person_id, b.currency)):
                settlements.append(await uow.settlements.create_for_balance(
                    actor_id, balance.other_person_id, abs(balance.net_minor),
                    balance.currency, context, datetime.now(UTC),
                ))
            await uow.commit()
            return tuple(settlements)
