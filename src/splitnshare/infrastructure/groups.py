"""Persist expense groups and enforce membership and invitation permissions."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from splitnshare.application.dto import GroupDTO, PersonDTO
from splitnshare.domain.enums import GroupRole, GroupStatus, MembershipStatus, PersonKind
from splitnshare.domain.errors import NotFoundError, PermissionDeniedError, ValidationError
from splitnshare.infrastructure.models import (
    GroupMembershipModel,
    GroupModel,
    GuestProfileModel,
    PersonModel,
    UserAccountModel,
)


class SqlAlchemyGroupRepository:
    """Keep groups and memberships within the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind group operations to a unit of work."""
        self._session = session

    async def list_for_person(self, person_id: UUID) -> tuple[GroupDTO, ...]:
        """Return groups with active membership ordered by name."""
        ids = (
            await self._session.scalars(
                select(GroupModel.id)
                .join(GroupMembershipModel)
                .where(
                    GroupMembershipModel.person_id == person_id,
                    GroupMembershipModel.status == MembershipStatus.ACTIVE,
                    GroupModel.status == GroupStatus.ACTIVE,
                )
                .order_by(GroupModel.name, GroupModel.id)
            )
        ).all()
        return tuple([await self.get(person_id, group_id) for group_id in ids])

    async def get(self, actor_id: UUID, group_id: UUID, *, for_update: bool = False) -> GroupDTO:
        """Authorize membership before exposing group names or participants."""
        model = await self._session.get(GroupModel, group_id, with_for_update=for_update)
        member = await self._session.get(GroupMembershipModel, (group_id, actor_id))
        actor = await self._session.get(PersonModel, actor_id)
        if model is None or model.status != GroupStatus.ACTIVE:
            raise NotFoundError("Active group not found.")
        if (
            member is None
            or member.status != MembershipStatus.ACTIVE
            or actor is None
            or actor.inactive_at is not None
        ):
            raise PermissionDeniedError("You must be an active group member.")
        if for_update:
            await self._session.execute(
                select(PersonModel)
                .join(GroupMembershipModel)
                .where(GroupMembershipModel.group_id == group_id)
                .order_by(PersonModel.id)
                .with_for_update(of=PersonModel)
            )
        rows = (
            await self._session.execute(
                select(PersonModel, UserAccountModel, GuestProfileModel)
                .join(GroupMembershipModel, GroupMembershipModel.person_id == PersonModel.id)
                .outerjoin(UserAccountModel, UserAccountModel.person_id == PersonModel.id)
                .outerjoin(GuestProfileModel, GuestProfileModel.person_id == PersonModel.id)
                .where(
                    GroupMembershipModel.group_id == group_id,
                    GroupMembershipModel.status == MembershipStatus.ACTIVE,
                    PersonModel.inactive_at.is_(None),
                )
                .order_by(PersonModel.display_name, PersonModel.id)
            )
        ).all()
        return GroupDTO(
            id=model.id,
            name=model.name,
            default_currency=model.default_currency,
            owner_person_id=model.creator_person_id,
            participants=tuple(
                PersonDTO(
                    id=person.id,
                    display_name=person.display_name,
                    kind=person.kind,
                    registered=account is not None and account.telegram_user_id is not None,
                    username=(
                        account.username if account else guest.suggested_username if guest else None
                    ),
                    telegram_user_id=account.telegram_user_id if account else None,
                )
                for person, account, guest in rows
            ),
        )

    async def _validate_invitees(self, actor_id: UUID, members: Sequence[UUID]) -> None:
        """Allow active registered people and guests owned by the inviter."""
        actor = await self._session.get(UserAccountModel, actor_id)
        if actor is None or actor.telegram_user_id is None:
            raise PermissionDeniedError("Only registered users can manage groups.")
        for person_id in set(members) | {actor_id}:
            person = await self._session.get(PersonModel, person_id)
            if person is None or person.inactive_at is not None:
                raise NotFoundError("A selected participant is no longer available.")
            if person.kind == PersonKind.GUEST:
                guest = await self._session.get(GuestProfileModel, person_id)
                if guest is None or guest.owner_person_id != actor_id:
                    raise PermissionDeniedError("Only your own guests can be invited.")

    async def create(
        self,
        actor_id: UUID,
        name: str,
        currency: str,
        members: Sequence[UUID],
    ) -> GroupDTO:
        """Create an owner and at least one additional participant atomically."""
        member_ids = set(members) | {actor_id}
        if len(member_ids) < 2:
            raise ValidationError("A group needs at least two participants.")
        await self._validate_invitees(actor_id, tuple(member_ids))
        model = GroupModel(name=name, default_currency=currency, creator_person_id=actor_id)
        self._session.add(model)
        await self._session.flush()
        for person_id in member_ids:
            self._session.add(
                GroupMembershipModel(
                    group_id=model.id,
                    person_id=person_id,
                    role=GroupRole.OWNER if person_id == actor_id else GroupRole.MEMBER,
                )
            )
        await self._session.flush()
        return await self.get(actor_id, model.id)

    async def add_members(
        self,
        actor_id: UUID,
        group_id: UUID,
        members: Sequence[UUID],
    ) -> tuple[GroupDTO, tuple[UUID, ...]]:
        """Serialize owner invitations and distinguish new from existing members."""
        group = await self.get(actor_id, group_id, for_update=True)
        if group.owner_person_id != actor_id:
            raise PermissionDeniedError("Only the group owner can add participants.")
        await self._validate_invitees(actor_id, members)
        added = []
        for person_id in set(members):
            member = await self._session.get(GroupMembershipModel, (group_id, person_id))
            if member is None:
                self._session.add(GroupMembershipModel(group_id=group_id, person_id=person_id))
                added.append(person_id)
            elif member.status != MembershipStatus.ACTIVE:
                member.status = MembershipStatus.ACTIVE
                added.append(person_id)
        await self._session.flush()
        return await self.get(actor_id, group_id), tuple(added)
