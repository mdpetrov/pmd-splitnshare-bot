from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Select

from splitnshare.application.dto import (
    BalanceDTO,
    ExpenseDTO,
    ExpensePage,
    ExpenseSplitDTO,
    FriendDTO,
    GuestDTO,
    NewExpenseRecord,
    PersonDTO,
    SharedTelegramUser,
    TelegramIdentity,
    TransferPreviewDTO,
    TransferResultDTO,
    UserSettingsDTO,
)
from splitnshare.domain.contexts import DirectExpenseContext, ExpenseContext, GroupExpenseContext
from splitnshare.domain.enums import (
    FriendSource,
    GroupRole,
    GuestCreationMethod,
    GuestTransferStatus,
    Language,
    MembershipStatus,
    PersonKind,
    TransferStatus,
)
from splitnshare.domain.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from splitnshare.domain.money import Money
from splitnshare.infrastructure.models import (
    DebtModel,
    ExpenseModel,
    ExpenseSplitModel,
    FriendshipModel,
    GroupMembershipModel,
    GroupModel,
    GuestProfileModel,
    GuestTransferModel,
    PersonModel,
    UserAccountModel,
    UserSettingsModel,
)


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register_or_update(self, identity: TelegramIdentity) -> PersonDTO:
        statement = (
            select(UserAccountModel, PersonModel)
            .join(PersonModel, PersonModel.id == UserAccountModel.person_id)
            .where(UserAccountModel.telegram_user_id == identity.telegram_user_id)
        )
        row = (await self._session.execute(statement)).one_or_none()
        now = datetime.now(UTC)
        if row is None:
            person = PersonModel(display_name=identity.display_name, kind=PersonKind.USER)
            self._session.add(person)
            await self._session.flush()
            account = UserAccountModel(
                person_id=person.id,
                telegram_user_id=identity.telegram_user_id,
                username=identity.username,
                first_name=identity.first_name,
                last_name=identity.last_name,
                registered_at=now,
                last_seen_at=now,
            )
            self._session.add(account)
        else:
            account, person = row
            person.display_name = identity.display_name
            account.username = identity.username
            account.first_name = identity.first_name
            account.last_name = identity.last_name
            account.last_seen_at = now
        await self._session.flush()
        return _person_dto(person, account)

    async def find_registered_by_telegram_id(self, telegram_user_id: int) -> PersonDTO | None:
        statement = (
            select(UserAccountModel, PersonModel)
            .join(PersonModel, PersonModel.id == UserAccountModel.person_id)
            .where(UserAccountModel.telegram_user_id == telegram_user_id)
        )
        row = (await self._session.execute(statement)).one_or_none()
        return _person_dto(row[1], row[0]) if row else None

    async def get_registered(self, person_id: UUID, *, for_update: bool = False) -> PersonDTO:
        statement = (
            select(UserAccountModel, PersonModel)
            .join(PersonModel, PersonModel.id == UserAccountModel.person_id)
            .where(UserAccountModel.person_id == person_id)
        )
        if for_update:
            statement = statement.with_for_update()
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            raise NotFoundError("Registered user not found.")
        return _person_dto(row[1], row[0])


class SqlAlchemyUserSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, person_id: UUID) -> UserSettingsDTO | None:
        model = await self._session.get(UserSettingsModel, person_id)
        return _settings_dto(model) if model is not None else None

    async def find_by_telegram_id(self, telegram_user_id: int) -> UserSettingsDTO | None:
        model = await self._session.scalar(
            select(UserSettingsModel)
            .join(UserAccountModel, UserAccountModel.person_id == UserSettingsModel.person_id)
            .where(UserAccountModel.telegram_user_id == telegram_user_id)
        )
        return _settings_dto(model) if model is not None else None

    async def create(
        self, person_id: UUID, default_currency: str, language: str
    ) -> UserSettingsDTO:
        await _require_registered(self._session, person_id)
        model = UserSettingsModel(
            person_id=person_id,
            default_currency=default_currency,
            language=Language(language),
        )
        self._session.add(model)
        await self._session.flush()
        return _settings_dto(model)

    async def update(
        self,
        person_id: UUID,
        *,
        default_currency: str | None,
        language: str | None,
    ) -> UserSettingsDTO:
        model = await self._session.get(UserSettingsModel, person_id, with_for_update=True)
        if model is None:
            raise NotFoundError("User settings not found.")
        if default_currency is not None:
            model.default_currency = default_currency
        if language is not None:
            model.language = Language(language)
        await self._session.flush()
        return _settings_dto(model)


class SqlAlchemyFriendRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        owner_person_id: UUID,
        friend_person_id: UUID,
        source: FriendSource,
    ) -> FriendDTO:
        await _require_registered(self._session, owner_person_id)
        if owner_person_id == friend_person_id:
            raise ValidationError("A user cannot add themselves as a friend.")
        friend = await self._session.get(PersonModel, friend_person_id)
        if friend is None or friend.inactive_at is not None:
            raise NotFoundError("Active friend not found.")

        values = {
            "owner_person_id": owner_person_id,
            "friend_person_id": friend_person_id,
            "source": source,
            "archived_at": None,
        }
        bind = self._session.get_bind()
        if bind.dialect.name == "postgresql":
            postgresql_statement = postgresql_insert(FriendshipModel).values(**values)
            postgresql_statement = postgresql_statement.on_conflict_do_update(
                index_elements=["owner_person_id", "friend_person_id"],
                set_={"archived_at": None, "updated_at": func.now()},
            )
            await self._session.execute(postgresql_statement)
        elif bind.dialect.name == "sqlite":
            sqlite_statement = sqlite_insert(FriendshipModel).values(**values)
            sqlite_statement = sqlite_statement.on_conflict_do_update(
                index_elements=["owner_person_id", "friend_person_id"],
                set_={"archived_at": None, "updated_at": func.now()},
            )
            await self._session.execute(sqlite_statement)
        else:
            relationship = await self._session.get(
                FriendshipModel, (owner_person_id, friend_person_id)
            )
            if relationship is None:
                self._session.add(FriendshipModel(**values))
            else:
                relationship.archived_at = None
        await self._session.flush()
        return await self._get_dto(owner_person_id, friend_person_id)

    async def list_active(self, owner_person_id: UUID) -> Sequence[FriendDTO]:
        await _require_registered(self._session, owner_person_id)
        rows = (
            await self._session.execute(
                select(
                    FriendshipModel,
                    PersonModel,
                    UserAccountModel,
                    GuestProfileModel,
                )
                .join(PersonModel, PersonModel.id == FriendshipModel.friend_person_id)
                .outerjoin(UserAccountModel, UserAccountModel.person_id == PersonModel.id)
                .outerjoin(GuestProfileModel, GuestProfileModel.person_id == PersonModel.id)
                .where(
                    FriendshipModel.owner_person_id == owner_person_id,
                    FriendshipModel.archived_at.is_(None),
                    PersonModel.inactive_at.is_(None),
                )
                .order_by(PersonModel.display_name, PersonModel.id)
            )
        ).all()
        return tuple(
            _friend_dto(relationship, person, account, guest)
            for relationship, person, account, guest in rows
        )

    async def archive(self, owner_person_id: UUID, friend_person_id: UUID) -> bool:
        await _require_registered(self._session, owner_person_id)
        relationship = await self._session.get(
            FriendshipModel,
            (owner_person_id, friend_person_id),
            with_for_update=True,
        )
        if relationship is None or relationship.archived_at is not None:
            return False
        relationship.archived_at = datetime.now(UTC)
        await self._session.flush()
        return True

    async def _get_dto(
        self, owner_person_id: UUID, friend_person_id: UUID
    ) -> FriendDTO:
        row = (
            await self._session.execute(
                select(
                    FriendshipModel,
                    PersonModel,
                    UserAccountModel,
                    GuestProfileModel,
                )
                .join(PersonModel, PersonModel.id == FriendshipModel.friend_person_id)
                .outerjoin(UserAccountModel, UserAccountModel.person_id == PersonModel.id)
                .outerjoin(GuestProfileModel, GuestProfileModel.person_id == PersonModel.id)
                .where(
                    FriendshipModel.owner_person_id == owner_person_id,
                    FriendshipModel.friend_person_id == friend_person_id,
                )
            )
        ).one()
        return _friend_dto(row[0], row[1], row[2], row[3])

class SqlAlchemyGuestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_telegram_guest(
        self, owner_person_id: UUID, shared: SharedTelegramUser
    ) -> PersonDTO:
        await _require_registered(self._session, owner_person_id)
        statement = (
            select(GuestProfileModel, PersonModel)
            .join(PersonModel, PersonModel.id == GuestProfileModel.person_id)
            .where(
                GuestProfileModel.owner_person_id == owner_person_id,
                GuestProfileModel.suggested_telegram_user_id == shared.telegram_user_id,
                GuestProfileModel.status == GuestTransferStatus.ACTIVE,
            )
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row:
            guest, person = row
            person.display_name = shared.display_name
            guest.suggested_username = shared.username
            await self._session.flush()
            return _person_dto(
                person,
                telegram_user_id=guest.suggested_telegram_user_id,
                username=guest.suggested_username,
            )

        person = PersonModel(display_name=shared.display_name, kind=PersonKind.GUEST)
        self._session.add(person)
        await self._session.flush()
        self._session.add(
            GuestProfileModel(
                person_id=person.id,
                owner_person_id=owner_person_id,
                suggested_telegram_user_id=shared.telegram_user_id,
                suggested_username=shared.username,
                creation_method=GuestCreationMethod.TELEGRAM,
            )
        )
        await self._session.flush()
        return _person_dto(
            person,
            telegram_user_id=shared.telegram_user_id,
            username=shared.username,
        )

    async def create_manual_guest(self, owner_person_id: UUID, display_name: str) -> PersonDTO:
        await _require_registered(self._session, owner_person_id)
        person = PersonModel(display_name=display_name, kind=PersonKind.GUEST)
        self._session.add(person)
        await self._session.flush()
        self._session.add(
            GuestProfileModel(
                person_id=person.id,
                owner_person_id=owner_person_id,
                creation_method=GuestCreationMethod.MANUAL,
            )
        )
        await self._session.flush()
        return _person_dto(person)

    async def list_owned(self, owner_person_id: UUID) -> Sequence[GuestDTO]:
        target_account = aliased(UserAccountModel)
        target_person = aliased(PersonModel)
        statement = (
            select(GuestProfileModel, PersonModel, target_account, target_person)
            .join(PersonModel, PersonModel.id == GuestProfileModel.person_id)
            .outerjoin(
                target_account,
                target_account.telegram_user_id
                == GuestProfileModel.suggested_telegram_user_id,
            )
            .outerjoin(
                target_person,
                and_(
                    target_person.id == target_account.person_id,
                    target_person.inactive_at.is_(None),
                ),
            )
            .where(
                GuestProfileModel.owner_person_id == owner_person_id,
                GuestProfileModel.status == GuestTransferStatus.ACTIVE,
                PersonModel.inactive_at.is_(None),
            )
            .order_by(PersonModel.display_name, PersonModel.id)
        )
        rows = (await self._session.execute(statement)).all()
        return tuple(
            GuestDTO(
                person_id=person.id,
                display_name=person.display_name,
                creation_method=guest.creation_method,
                suggested_telegram_user_id=guest.suggested_telegram_user_id,
                username=guest.suggested_username,
                suggested_target_person_id=(
                    target.id
                    if target is not None and target.id != owner_person_id
                    else None
                ),
                suggested_target_name=(
                    target.display_name
                    if target is not None and target.id != owner_person_id
                    else None
                ),
                suggested_target_username=(
                    account.username
                    if account is not None
                    and target is not None
                    and target.id != owner_person_id
                    else None
                ),
            )
            for guest, person, account, target in rows
        )

    async def preview_transfer(
        self, actor_person_id: UUID, guest_person_id: UUID, target_person_id: UUID
    ) -> TransferPreviewDTO:
        guest, guest_person = await self._get_owned_active(
            actor_person_id, guest_person_id, for_update=False
        )
        target_account, target_person = await _get_registered_row(
            self._session, target_person_id, for_update=False
        )
        _validate_transfer(actor_person_id, guest, target_person)
        expense_ids = await _affected_expense_ids(self._session, guest_person_id)
        group_count = int(
            await self._session.scalar(
                select(func.count())
                .select_from(GroupMembershipModel)
                .where(GroupMembershipModel.person_id == guest_person_id)
            )
            or 0
        )
        friendship_count = int(
            await self._session.scalar(
                select(func.count())
                .select_from(FriendshipModel)
                .where(FriendshipModel.friend_person_id == guest_person_id)
            )
            or 0
        )
        totals: dict[str, int] = defaultdict(int)
        if expense_ids:
            rows = (
                await self._session.execute(
                    select(DebtModel.currency, DebtModel.amount_minor).where(
                        DebtModel.expense_id.in_(expense_ids),
                        or_(
                            DebtModel.debtor_person_id == guest_person_id,
                            DebtModel.creditor_person_id == guest_person_id,
                        ),
                    )
                )
            ).all()
            for currency, amount in rows:
                totals[currency] += amount
        return TransferPreviewDTO(
            guest_person_id=guest_person.id,
            guest_name=guest_person.display_name,
            target_person_id=target_person.id,
            target_name=target_person.display_name,
            expense_count=len(expense_ids),
            group_count=group_count,
            friendship_count=friendship_count,
            debt_totals=dict(totals),
            guest_username=guest.suggested_username,
            target_username=target_account.username,
        )

    async def transfer_all(
        self, actor_person_id: UUID, guest_person_id: UUID, target_person_id: UUID
    ) -> TransferResultDTO:
        guest, guest_person = await self._get_owned_active(
            actor_person_id, guest_person_id, for_update=True
        )
        target_account, target_person = await _get_registered_row(
            self._session, target_person_id, for_update=True
        )
        _validate_transfer(actor_person_id, guest, target_person)

        expense_ids = await _affected_expense_ids(self._session, guest_person_id)
        overlap_count = 0
        for expense_id in expense_ids:
            expense = await self._session.get(ExpenseModel, expense_id)
            if expense is None:
                raise ConflictError("An affected expense disappeared during transfer.")
            source_split = await self._session.get(
                ExpenseSplitModel, (expense_id, guest_person_id)
            )
            target_split = await self._session.get(
                ExpenseSplitModel, (expense_id, target_person_id)
            )
            if source_split is not None and target_split is not None:
                overlap_count += 1
                new_position = min(source_split.position, target_split.position)
                target_split.owed_minor += source_split.owed_minor
                await self._session.delete(source_split)
                await self._session.flush()
                target_split.position = new_position
            elif source_split is not None:
                source_split.person_id = target_person_id

            if expense.payer_person_id == guest_person_id:
                expense.payer_person_id = target_person_id
            await self._session.flush()
            await _normalize_positions(self._session, expense_id)
            await _rebuild_debts(self._session, expense)

        membership_rows = (
            await self._session.execute(
                select(GroupMembershipModel).where(
                    GroupMembershipModel.person_id == guest_person_id
                )
            )
        ).scalars().all()
        membership_count = len(membership_rows)
        duplicate_memberships = 0
        for source_membership in membership_rows:
            target_membership = await self._session.get(
                GroupMembershipModel, (source_membership.group_id, target_person_id)
            )
            if target_membership is not None:
                duplicate_memberships += 1
                await self._session.delete(source_membership)
            else:
                source_membership.person_id = target_person_id
                source_membership.role = GroupRole.MEMBER
        await self._session.flush()

        friendship_rows = (
            await self._session.execute(
                select(FriendshipModel)
                .where(FriendshipModel.friend_person_id == guest_person_id)
                .with_for_update()
            )
        ).scalars().all()
        friendship_count = len(friendship_rows)
        duplicate_friendships = 0
        self_friendships = 0
        for source_friendship in friendship_rows:
            if source_friendship.owner_person_id == target_person_id:
                self_friendships += 1
                await self._session.delete(source_friendship)
                continue
            target_friendship = await self._session.get(
                FriendshipModel,
                (source_friendship.owner_person_id, target_person_id),
                with_for_update=True,
            )
            if target_friendship is not None:
                duplicate_friendships += 1
                if source_friendship.archived_at is None:
                    target_friendship.archived_at = None
                await self._session.delete(source_friendship)
            else:
                source_friendship.friend_person_id = target_person_id
        await self._session.flush()

        now = datetime.now(UTC)
        guest.status = GuestTransferStatus.TRANSFERRED
        guest.transferred_to_person_id = target_person_id
        guest_person.inactive_at = now
        affected_counts = {
            "expenses": len(expense_ids),
            "overlapping_splits": overlap_count,
            "group_memberships": membership_count,
            "duplicate_memberships": duplicate_memberships,
            "friendships": friendship_count,
            "duplicate_friendships": duplicate_friendships,
            "self_friendships": self_friendships,
        }
        transfer = GuestTransferModel(
            source_guest_person_id=guest_person_id,
            target_user_person_id=target_person_id,
            initiated_by_person_id=actor_person_id,
            status=TransferStatus.COMPLETED,
            source_name_snapshot=guest_person.display_name,
            affected_counts=affected_counts,
            completed_at=now,
        )
        self._session.add(transfer)
        await self._session.flush()
        return TransferResultDTO(
            transfer_id=transfer.id,
            target_person_id=target_person.id,
            target_telegram_user_id=target_account.telegram_user_id,
            target_name=target_person.display_name,
            target_username=target_account.username,
            affected_counts=affected_counts,
        )

    async def _get_owned_active(
        self, actor_person_id: UUID, guest_person_id: UUID, *, for_update: bool
    ) -> tuple[GuestProfileModel, PersonModel]:
        statement = (
            select(GuestProfileModel, PersonModel)
            .join(PersonModel, PersonModel.id == GuestProfileModel.person_id)
            .where(GuestProfileModel.person_id == guest_person_id)
        )
        if for_update:
            statement = statement.with_for_update()
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            raise NotFoundError("Guest not found.")
        guest, person = row
        if guest.owner_person_id != actor_person_id:
            raise PermissionDeniedError("Only the guest owner can transfer this guest.")
        if guest.status is not GuestTransferStatus.ACTIVE or person.inactive_at is not None:
            raise ConflictError("This guest has already been transferred or is inactive.")
        return guest, person


class SqlAlchemyExpenseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: NewExpenseRecord) -> ExpenseDTO:
        command = record.command
        await _require_registered(self._session, command.creator_person_id)
        rows = (
            await self._session.execute(
                select(PersonModel.id, PersonModel.inactive_at).where(
                    PersonModel.id.in_(command.participant_ids)
                )
            )
        ).all()
        if len(rows) != len(command.participant_ids):
            raise NotFoundError("One or more participants do not exist.")
        if any(inactive_at is not None for _, inactive_at in rows):
            raise ValidationError("Inactive guests cannot be added to an expense.")

        group_id = command.context.group_id
        if isinstance(command.context, GroupExpenseContext):
            group = await self._session.get(GroupModel, group_id)
            if group is None or group.status.value != "active":
                raise NotFoundError("Active group not found.")
            required_members = set(command.participant_ids) | {command.creator_person_id}
            active_members = set(
                (
                    await self._session.execute(
                        select(GroupMembershipModel.person_id).where(
                            GroupMembershipModel.group_id == group_id,
                            GroupMembershipModel.status == MembershipStatus.ACTIVE,
                            GroupMembershipModel.person_id.in_(required_members),
                        )
                    )
                ).scalars().all()
            )
            if active_members != required_members:
                raise PermissionDeniedError(
                    "The creator and every participant must be active group members."
                )
        expense = ExpenseModel(
            group_id=group_id,
            creator_person_id=command.creator_person_id,
            payer_person_id=record.payer_person_id,
            description=command.description,
            total_minor=command.total.minor,
            currency=command.total.currency,
            split_method=command.split_method,
        )
        self._session.add(expense)
        await self._session.flush()
        for allocation in record.allocations:
            self._session.add(
                ExpenseSplitModel(
                    expense_id=expense.id,
                    person_id=allocation.person_id,
                    owed_minor=allocation.owed_minor,
                    position=allocation.position,
                )
            )
            if allocation.person_id != record.payer_person_id and allocation.owed_minor > 0:
                self._session.add(
                    DebtModel(
                        expense_id=expense.id,
                        debtor_person_id=allocation.person_id,
                        creditor_person_id=record.payer_person_id,
                        amount_minor=allocation.owed_minor,
                        currency=command.total.currency,
                    )
                )
        await self._session.flush()
        return await self._to_dto(expense)

    async def soft_delete(self, actor_person_id: UUID, expense_id: UUID) -> bool:
        expense = await self._session.get(ExpenseModel, expense_id, with_for_update=True)
        if expense is None:
            raise NotFoundError("Expense not found.")
        if expense.creator_person_id != actor_person_id:
            raise PermissionDeniedError("Only the expense creator can delete it.")
        if expense.deleted_at is not None:
            return False
        expense.deleted_at = datetime.now(UTC)
        expense.deleted_by_person_id = actor_person_id
        await self._session.flush()
        return True

    async def get(self, viewer_person_id: UUID, expense_id: UUID) -> ExpenseDTO:
        expense = await self._session.get(ExpenseModel, expense_id)
        if expense is None or expense.deleted_at is not None:
            raise NotFoundError("Expense not found.")
        visible = await self._session.scalar(
            select(func.count())
            .select_from(ExpenseSplitModel)
            .where(
                ExpenseSplitModel.expense_id == expense_id,
                ExpenseSplitModel.person_id == viewer_person_id,
            )
        )
        if not visible and expense.creator_person_id != viewer_person_id:
            raise PermissionDeniedError("You cannot view this expense.")
        return await self._to_dto(expense)

    async def list_for_person(
        self,
        person_id: UUID,
        context: ExpenseContext | None,
        cursor: str | None,
        limit: int,
    ) -> ExpensePage:
        statement = (
            select(ExpenseModel)
            .join(ExpenseSplitModel, ExpenseSplitModel.expense_id == ExpenseModel.id)
            .where(
                ExpenseSplitModel.person_id == person_id,
                ExpenseModel.deleted_at.is_(None),
            )
        )
        statement = _apply_context(statement, context)
        if cursor:
            cursor_id = _decode_cursor(cursor)
            cursor_date = await self._session.scalar(
                select(ExpenseModel.created_at).where(ExpenseModel.id == cursor_id)
            )
            if cursor_date is None:
                raise ValidationError("Invalid pagination cursor.")
            statement = statement.where(
                or_(
                    ExpenseModel.created_at < cursor_date,
                    and_(ExpenseModel.created_at == cursor_date, ExpenseModel.id < cursor_id),
                )
            )
        statement = statement.order_by(
            ExpenseModel.created_at.desc(), ExpenseModel.id.desc()
        ).limit(limit + 1)
        expenses = list((await self._session.execute(statement)).scalars().unique().all())
        has_more = len(expenses) > limit
        expenses = expenses[:limit]
        items = tuple([await self._to_dto(expense) for expense in expenses])
        next_cursor = _encode_cursor(expenses[-1]) if has_more and expenses else None
        return ExpensePage(items=items, next_cursor=next_cursor)

    async def balances(
        self, person_id: UUID, context: ExpenseContext | None
    ) -> Sequence[BalanceDTO]:
        statement = (
            select(DebtModel)
            .join(ExpenseModel, ExpenseModel.id == DebtModel.expense_id)
            .where(
                ExpenseModel.deleted_at.is_(None),
                or_(
                    DebtModel.debtor_person_id == person_id,
                    DebtModel.creditor_person_id == person_id,
                ),
            )
        )
        statement = _apply_context(statement, context)
        debts = (await self._session.execute(statement)).scalars().all()
        totals: dict[tuple[UUID, str], int] = defaultdict(int)
        for debt in debts:
            if debt.creditor_person_id == person_id:
                totals[(debt.debtor_person_id, debt.currency)] += debt.amount_minor
            else:
                totals[(debt.creditor_person_id, debt.currency)] -= debt.amount_minor
        person_ids = {key[0] for key in totals}
        people: dict[UUID, tuple[str, str | None]] = {}
        if person_ids:
            name_rows = (
                await self._session.execute(
                    select(
                        PersonModel.id,
                        PersonModel.display_name,
                        UserAccountModel.username,
                        GuestProfileModel.suggested_username,
                    )
                    .outerjoin(UserAccountModel, UserAccountModel.person_id == PersonModel.id)
                    .outerjoin(GuestProfileModel, GuestProfileModel.person_id == PersonModel.id)
                    .where(PersonModel.id.in_(person_ids))
                )
            ).tuples().all()
            people = {
                other_id: (display_name, account_username or guest_username)
                for other_id, display_name, account_username, guest_username in name_rows
            }
        return tuple(
            BalanceDTO(
                other_person_id=other_id,
                other_name=people[other_id][0],
                currency=currency,
                net_minor=net,
                username=people[other_id][1],
            )
            for (other_id, currency), net in sorted(
                totals.items(),
                key=lambda item: (people[item[0][0]][0].casefold(), item[0][1]),
            )
            if net != 0
        )

    async def recent_people(self, person_id: UUID, limit: int) -> Sequence[PersonDTO]:
        recent_expense_ids = list(
            (
                await self._session.execute(
                    select(ExpenseModel.id)
                    .join(ExpenseSplitModel, ExpenseSplitModel.expense_id == ExpenseModel.id)
                    .where(
                        ExpenseSplitModel.person_id == person_id,
                        ExpenseModel.deleted_at.is_(None),
                    )
                    .order_by(ExpenseModel.created_at.desc(), ExpenseModel.id.desc())
                    .limit(50)
                )
            ).scalars().all()
        )
        people: list[PersonDTO] = []
        seen = {person_id}
        for expense_id in recent_expense_ids:
            rows = (
                await self._session.execute(
                    select(PersonModel, UserAccountModel, GuestProfileModel)
                    .join(ExpenseSplitModel, ExpenseSplitModel.person_id == PersonModel.id)
                    .outerjoin(UserAccountModel, UserAccountModel.person_id == PersonModel.id)
                    .outerjoin(GuestProfileModel, GuestProfileModel.person_id == PersonModel.id)
                    .where(
                        ExpenseSplitModel.expense_id == expense_id,
                        PersonModel.inactive_at.is_(None),
                    )
                    .order_by(ExpenseSplitModel.position)
                )
            ).all()
            for person, account, guest in rows:
                if person.id in seen:
                    continue
                seen.add(person.id)
                people.append(
                    _person_dto(
                        person,
                        account,
                        username=guest.suggested_username if guest is not None else None,
                    )
                )
                if len(people) == limit:
                    return tuple(people)
        return tuple(people)

    async def _to_dto(self, expense: ExpenseModel) -> ExpenseDTO:
        split_rows = (
            await self._session.execute(
                select(
                    ExpenseSplitModel,
                    PersonModel,
                    UserAccountModel,
                    GuestProfileModel,
                )
                .join(PersonModel, PersonModel.id == ExpenseSplitModel.person_id)
                .outerjoin(UserAccountModel, UserAccountModel.person_id == PersonModel.id)
                .outerjoin(GuestProfileModel, GuestProfileModel.person_id == PersonModel.id)
                .where(ExpenseSplitModel.expense_id == expense.id)
                .order_by(ExpenseSplitModel.position)
            )
        ).all()
        payer_row = (
            await self._session.execute(
                select(PersonModel, UserAccountModel, GuestProfileModel)
                .outerjoin(UserAccountModel, UserAccountModel.person_id == PersonModel.id)
                .outerjoin(GuestProfileModel, GuestProfileModel.person_id == PersonModel.id)
                .where(PersonModel.id == expense.payer_person_id)
            )
        ).one()
        payer, payer_account, payer_guest = payer_row
        return ExpenseDTO(
            id=expense.id,
            creator_person_id=expense.creator_person_id,
            payer_person_id=expense.payer_person_id,
            payer_name=payer.display_name,
            payer_username=(
                payer_account.username
                if payer_account is not None
                else payer_guest.suggested_username if payer_guest is not None else None
            ),
            description=expense.description,
            total=Money(expense.total_minor, expense.currency),
            split_method=expense.split_method,
            group_id=expense.group_id,
            created_at=expense.created_at,
            splits=tuple(
                ExpenseSplitDTO(
                    person_id=split.person_id,
                    display_name=person.display_name,
                    username=(
                        account.username
                        if account is not None
                        else guest.suggested_username if guest is not None else None
                    ),
                    owed_minor=split.owed_minor,
                    position=split.position,
                )
                for split, person, account, guest in split_rows
            ),
        )


async def _get_registered_row(
    session: AsyncSession, person_id: UUID, *, for_update: bool
) -> tuple[UserAccountModel, PersonModel]:
    statement = (
        select(UserAccountModel, PersonModel)
        .join(PersonModel, PersonModel.id == UserAccountModel.person_id)
        .where(UserAccountModel.person_id == person_id)
    )
    if for_update:
        statement = statement.with_for_update()
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise NotFoundError("The transfer target must be a registered bot user.")
    return row[0], row[1]


async def _require_registered(session: AsyncSession, person_id: UUID) -> None:
    if not await session.scalar(
        select(func.count())
        .select_from(UserAccountModel)
        .where(UserAccountModel.person_id == person_id)
    ):
        raise PermissionDeniedError("A registered bot user is required.")


def _validate_transfer(
    actor_person_id: UUID, guest: GuestProfileModel, target_person: PersonModel
) -> None:
    if guest.owner_person_id != actor_person_id:
        raise PermissionDeniedError("Only the guest owner can transfer this guest.")
    if actor_person_id == target_person.id:
        raise ValidationError("A guest cannot be transferred to its owner.")
    if target_person.inactive_at is not None or target_person.kind is not PersonKind.USER:
        raise ValidationError("The target must be an active registered user.")


async def _affected_expense_ids(session: AsyncSession, guest_person_id: UUID) -> list[UUID]:
    rows = await session.execute(
        select(ExpenseModel.id)
        .outerjoin(ExpenseSplitModel, ExpenseSplitModel.expense_id == ExpenseModel.id)
        .where(
            or_(
                ExpenseModel.payer_person_id == guest_person_id,
                ExpenseSplitModel.person_id == guest_person_id,
            )
        )
        .distinct()
    )
    return list(rows.scalars().all())


async def _normalize_positions(session: AsyncSession, expense_id: UUID) -> None:
    splits = (
        await session.execute(
            select(ExpenseSplitModel)
            .where(ExpenseSplitModel.expense_id == expense_id)
            .order_by(ExpenseSplitModel.position, ExpenseSplitModel.person_id)
        )
    ).scalars().all()
    # Move positions out of the constrained range before making them contiguous.
    for index, split in enumerate(splits):
        split.position = 1000 + index
    await session.flush()
    for index, split in enumerate(splits):
        split.position = index
    await session.flush()


async def _rebuild_debts(session: AsyncSession, expense: ExpenseModel) -> None:
    await session.execute(delete(DebtModel).where(DebtModel.expense_id == expense.id))
    splits = (
        await session.execute(
            select(ExpenseSplitModel).where(ExpenseSplitModel.expense_id == expense.id)
        )
    ).scalars().all()
    if sum(split.owed_minor for split in splits) != expense.total_minor:
        raise ConflictError("Expense splits no longer match the total.")
    for split in splits:
        if split.person_id != expense.payer_person_id and split.owed_minor > 0:
            session.add(
                DebtModel(
                    expense_id=expense.id,
                    debtor_person_id=split.person_id,
                    creditor_person_id=expense.payer_person_id,
                    amount_minor=split.owed_minor,
                    currency=expense.currency,
                )
            )
    await session.flush()


def _person_dto(
    person: PersonModel,
    account: UserAccountModel | None = None,
    telegram_user_id: int | None = None,
    username: str | None = None,
) -> PersonDTO:
    return PersonDTO(
        id=person.id,
        display_name=person.display_name,
        kind=person.kind,
        registered=account is not None,
        username=account.username if account else username,
        telegram_user_id=account.telegram_user_id if account else telegram_user_id,
    )


def _settings_dto(model: UserSettingsModel) -> UserSettingsDTO:
    return UserSettingsDTO(
        person_id=model.person_id,
        default_currency=model.default_currency,
        language=model.language,
    )


def _friend_dto(
    relationship: FriendshipModel,
    person: PersonModel,
    account: UserAccountModel | None,
    guest: GuestProfileModel | None,
) -> FriendDTO:
    return FriendDTO(
        person_id=person.id,
        display_name=person.display_name,
        kind=person.kind,
        registered=account is not None,
        source=relationship.source,
        username=(
            account.username
            if account is not None
            else guest.suggested_username if guest is not None else None
        ),
        telegram_user_id=(
            account.telegram_user_id
            if account is not None
            else guest.suggested_telegram_user_id if guest is not None else None
        ),
    )


def _apply_context(statement: Select[Any], context: ExpenseContext | None) -> Select[Any]:
    if isinstance(context, DirectExpenseContext):
        return statement.where(ExpenseModel.group_id.is_(None))
    if isinstance(context, GroupExpenseContext):
        return statement.where(ExpenseModel.group_id == context.group_id)
    return statement


def _encode_cursor(expense: ExpenseModel) -> str:
    return str(expense.id)


def _decode_cursor(cursor: str) -> UUID:
    try:
        return UUID(cursor)
    except ValueError as exc:
        raise ValidationError("Invalid pagination cursor.") from exc
