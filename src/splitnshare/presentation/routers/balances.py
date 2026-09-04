"""Handle balance display and full or partial settlement flows."""

from collections.abc import Sequence
from datetime import UTC, datetime
from html import escape
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from splitnshare.application.dto import (
    ActivityItemDTO,
    BalanceDTO,
    ExpenseActivityDTO,
    SettleBalanceCommand,
    SettlementDTO,
)
from splitnshare.domain.contexts import DirectExpenseContext
from splitnshare.domain.enums import Language
from splitnshare.domain.errors import DomainError
from splitnshare.domain.money import Money
from splitnshare.presentation.callbacks import uuid_from_token, uuid_token
from splitnshare.presentation.container import Services
from splitnshare.presentation.formatters import (
    activity_text,
    balances_text,
    expense_text,
    person_balances_text,
    settlement_notification_text,
)
from splitnshare.presentation.helpers import (
    callback_message,
    callback_payload,
    current_person,
    parse_total,
)
from splitnshare.presentation.i18n import button_values, translate
from splitnshare.presentation.keyboards import (
    balances_keyboard,
    cancel_keyboard,
    expense_details_keyboard,
    main_menu,
    person_activity_keyboard,
    person_balance_keyboard,
    settlement_amount_keyboard,
)
from splitnshare.presentation.labels import participant_html
from splitnshare.presentation.states import SettlementStates

router = Router(name="balances")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@router.message(F.text.in_(button_values("balances")))
async def balances(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Show the current user's direct balances from a reply-menu action."""
    await state.clear()
    person = await current_person(message, services)
    current_balances = await services.balances.get_balances(person.id)
    await message.answer(
        balances_text(current_balances, language),
        reply_markup=balances_keyboard(current_balances, language),
    )


@router.callback_query(F.data == "menu:balances")
async def balances_callback(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Replace the current message with the user's direct balances."""
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    await state.clear()
    current_balances = await services.balances.get_balances(person.id)
    await target_message.edit_text(
        balances_text(current_balances, language),
        reply_markup=balances_keyboard(current_balances, language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("balance:person:"))
async def show_person_balance(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Show every currency balance and action for one counterparty."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    try:
        other_id = uuid_from_token(payload.rsplit(":", 1)[1])
    except ValueError:
        await callback.answer(translate(language, "balance_person_stale"), show_alert=True)
        return
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    selected = _balances_with(await services.balances.get_balances(person.id), other_id)
    if not selected:
        await callback.answer(translate(language, "balance_person_stale"), show_alert=True)
        return
    await state.clear()
    await target_message.edit_text(
        person_balances_text(selected, language),
        reply_markup=person_balance_keyboard(selected, language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("balance:history:"))
@router.callback_query(F.data.startswith("friend:history:"))
async def show_person_history(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Show the first active expense page shared with one counterparty."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    origin = "friend" if payload.startswith("friend:history:") else "balance"
    try:
        other_id = uuid_from_token(payload.rsplit(":", 1)[1])
    except ValueError:
        await callback.answer(translate(language, "balance_person_stale"), show_alert=True)
        return
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    page = await services.activities.list_for_person(
        person.id, other_person_id=other_id
    )
    settings = await services.user_settings.get_or_create(person.id)
    await target_message.edit_text(
        _person_history_text(
            page.items,
            person.id,
            other_id,
            language,
            settings.timezone or "UTC",
        ),
        reply_markup=person_activity_keyboard(
            page,
            other_id,
            language,
            settings.timezone or "UTC",
            origin,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ba:"))
@router.callback_query(F.data.startswith("fa:"))
async def show_person_history_page(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Replace shared history with its next cursor-paginated page."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    origin = "friend" if payload.startswith("fa:") else "balance"
    parts = payload.split(":")
    try:
        if len(parts) != 4:
            raise ValueError("Invalid shared-history callback.")
        other_id = uuid_from_token(parts[1])
        cursor = f"{parts[2]}:{parts[3]}"
    except ValueError:
        await callback.answer(translate(language, "balance_person_stale"), show_alert=True)
        return
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    page = await services.activities.list_for_person(
        person.id, other_person_id=other_id, cursor=cursor
    )
    settings = await services.user_settings.get_or_create(person.id)
    await target_message.edit_text(
        _person_history_text(
            page.items,
            person.id,
            other_id,
            language,
            settings.timezone or "UTC",
        ),
        reply_markup=person_activity_keyboard(
            page,
            other_id,
            language,
            settings.timezone or "UTC",
            origin,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bhv:"))
@router.callback_query(F.data.startswith("fhv:"))
async def view_person_history_expense(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Show expense details while preserving the counterparty history path."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    from_friend = payload.startswith("fhv:")
    parts = payload.split(":")
    try:
        if len(parts) != 3:
            raise ValueError("Invalid shared-expense callback.")
        other_id = uuid_from_token(parts[1])
        expense_id = uuid_from_token(parts[2])
    except ValueError:
        await callback.answer(translate(language, "balance_person_stale"), show_alert=True)
        return
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    expense = await services.expense_queries.get_details(person.id, expense_id)
    if not any(split.person_id == other_id for split in expense.splits):
        await callback.answer(translate(language, "balance_person_stale"), show_alert=True)
        return
    settings = await services.user_settings.get_or_create(person.id)
    await target_message.edit_text(
        expense_text(expense, language, settings.timezone or "UTC"),
        reply_markup=expense_details_keyboard(
            expense,
            person.id,
            language,
            back_callback=(
                f"friend:history:{uuid_token(other_id)}"
                if from_friend
                else f"balance:history:{uuid_token(other_id)}"
            ),
            back_label_key="transaction_history",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settle:select:"))
async def select_balance_to_settle(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Validate a selected balance and offer full or partial payment."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    parts = payload.split(":")
    if len(parts) != 4:
        await callback.answer(translate(language, "settlement_stale"), show_alert=True)
        return
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    try:
        other_id = UUID(parts[2])
    except ValueError:
        await callback.answer(translate(language, "settlement_stale"), show_alert=True)
        return
    currency = parts[3]
    current = _find_balance(
        await services.balances.get_balances(person.id), other_id, currency
    )
    if current is None:
        await callback.answer(translate(language, "settlement_stale"), show_alert=True)
        return
    await state.clear()
    await state.update_data(
        actor_id=str(person.id),
        other_id=str(other_id),
        currency=currency,
        outstanding_minor=abs(current.net_minor),
        net_minor=current.net_minor,
    )
    await state.set_state(SettlementStates.confirm)
    await target_message.edit_text(
        _settlement_prompt(current, language),
        reply_markup=settlement_amount_keyboard(
            Money(abs(current.net_minor), current.currency),
            language,
            back_callback=f"balance:person:{uuid_token(other_id)}",
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "settle:full")
async def settle_full_balance(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    bot: Bot,
    language: Language,
) -> None:
    """Record a payment for the complete outstanding balance."""
    if await state.get_state() != SettlementStates.confirm.state:
        await callback.answer(translate(language, "settlement_stale"), show_alert=True)
        return
    target_message = callback_message(callback)
    data = await state.get_data()
    try:
        settlement = await _record_settlement(
            services, data, int(data["outstanding_minor"])
        )
    except DomainError:
        await state.clear()
        await callback.answer(translate(language, "settlement_stale"), show_alert=True)
        return
    await state.clear()
    actor_id = UUID(str(data["actor_id"]))
    current_balances = await services.balances.get_balances(actor_id)
    await target_message.edit_text(
        translate(language, "settlement_saved", amount=settlement.amount.format())
        + "\n\n"
        + balances_text(current_balances, language),
        reply_markup=balances_keyboard(current_balances, language),
    )
    await callback.answer()
    await _notify_settlement_counterparty(bot, services, settlement)


@router.callback_query(F.data == "settle:partial")
async def request_partial_settlement(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Store the selected balance and prompt for a partial amount."""
    if await state.get_state() != SettlementStates.confirm.state:
        await callback.answer(translate(language, "settlement_stale"), show_alert=True)
        return
    target_message = callback_message(callback)
    data = await state.get_data()
    await state.set_state(SettlementStates.amount)
    await target_message.answer(
        translate(language, "settle_enter_amount", currency=data["currency"]),
        reply_markup=cancel_keyboard(language),
    )
    await callback.answer()


@router.message(SettlementStates.amount, F.text.in_(button_values("back")))
async def partial_settlement_back(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Leave partial entry and return to the current balance list."""
    await state.clear()
    person = await current_person(message, services)
    current_balances = await services.balances.get_balances(person.id)
    await message.answer(translate(language, "balances"), reply_markup=main_menu(language))
    await message.answer(
        balances_text(current_balances, language),
        reply_markup=balances_keyboard(current_balances, language),
    )


@router.message(SettlementStates.amount)
async def receive_partial_settlement(
    message: Message,
    state: FSMContext,
    services: Services,
    bot: Bot,
    language: Language,
) -> None:
    """Parse and record a user-entered partial settlement amount."""
    data = await state.get_data()
    currency = str(data["currency"])
    outstanding = Money(int(data["outstanding_minor"]), currency)
    try:
        amount = parse_total(message.text or "", currency)
    except DomainError:
        await message.answer(
            translate(language, "settle_invalid_amount", amount=outstanding.format())
        )
        return
    if amount.currency != currency:
        await message.answer(
            translate(language, "settle_wrong_currency", currency=currency)
        )
        return
    if amount.minor > outstanding.minor:
        await message.answer(
            translate(language, "settle_invalid_amount", amount=outstanding.format())
        )
        return
    try:
        settlement = await _record_settlement(services, data, amount.minor)
    except DomainError:
        await state.clear()
        await message.answer(translate(language, "settlement_stale"))
        return
    await state.clear()
    actor_id = UUID(str(data["actor_id"]))
    current_balances = await services.balances.get_balances(actor_id)
    await message.answer(
        translate(language, "settlement_saved", amount=amount.format()),
        reply_markup=main_menu(language),
    )
    await message.answer(
        balances_text(current_balances, language),
        reply_markup=balances_keyboard(current_balances, language),
    )
    await _notify_settlement_counterparty(bot, services, settlement)


def _balances_with(
    balances: Sequence[BalanceDTO], other_id: UUID
) -> tuple[BalanceDTO, ...]:
    """Return every currency balance associated with one counterparty."""
    return tuple(
        balance for balance in balances if balance.other_person_id == other_id
    )


def _person_history_text(
    items: Sequence[ActivityItemDTO],
    viewer_id: UUID,
    other_id: UUID,
    language: Language,
    timezone: str,
) -> str:
    """Render shared history with the selected participant in its heading."""
    if not items:
        return translate(language, "no_transactions_with_person")
    name, username = _activity_person_label(items[0], other_id)
    title = translate(
        language,
        "transactions_with",
        name=participant_html(name, other_id, username),
    )
    return activity_text(items, viewer_id, language, timezone, title)


def _activity_person_label(
    item: ActivityItemDTO, other_id: UUID
) -> tuple[str, str | None]:
    """Extract one counterparty label from an activity item."""
    if isinstance(item, ExpenseActivityDTO):
        split = next(
            split for split in item.expense.splits if split.person_id == other_id
        )
        return split.display_name, split.username
    settlement = item.settlement
    if settlement.payer_person_id == other_id:
        return item.payer_name, item.payer_username
    return item.recipient_name, item.recipient_username


def _find_balance(
    balances: Sequence[BalanceDTO],
    other_id: UUID,
    currency: str,
) -> BalanceDTO | None:
    """Find one counterparty-and-currency balance in a result sequence."""
    return next(
        (
            balance
            for balance in balances
            if balance.other_person_id == other_id and balance.currency == currency
        ),
        None,
    )


def _settlement_prompt(balance: BalanceDTO, language: Language) -> str:
    """Describe the settlement direction and outstanding amount."""
    return translate(
        language,
        "settle_you_pay" if balance.net_minor < 0 else "settle_other_pays",
        name=participant_html(
            balance.other_name, balance.other_person_id, balance.username
        ),
        amount=escape(Money(abs(balance.net_minor), balance.currency).format()),
    )


async def _record_settlement(
    services: Services, data: dict[str, object], amount_minor: int
) -> SettlementDTO:
    """Persist one direct settlement and return its committed record."""
    amount = Money(amount_minor, str(data["currency"]))
    return await services.settlements.settle(
        SettleBalanceCommand(
            actor_person_id=UUID(str(data["actor_id"])),
            other_person_id=UUID(str(data["other_id"])),
            amount=amount,
            context=DirectExpenseContext(),
            occurred_at=datetime.now(UTC),
        )
    )


async def _notify_settlement_counterparty(
    bot: Bot,
    services: Services,
    settlement: SettlementDTO,
) -> None:
    """Best-effort notify the registered counterparty after settlement commit."""
    registered = await services.users.list_registered(
        (
            settlement.recorded_by_person_id,
            settlement.payer_person_id,
            settlement.recipient_person_id,
        )
    )
    people = {person.id: person for person in registered}
    recorder = people.get(settlement.recorded_by_person_id)
    counterparty_id = (
        settlement.recipient_person_id
        if settlement.payer_person_id == settlement.recorded_by_person_id
        else settlement.payer_person_id
    )
    counterparty = people.get(counterparty_id)
    if (
        recorder is None
        or counterparty is None
        or counterparty.telegram_user_id is None
    ):
        return
    settings = await services.user_settings.find_by_telegram_id(
        counterparty.telegram_user_id
    )
    counterparty_language = (
        settings.language if settings is not None else Language.ENGLISH
    )
    try:
        await bot.send_message(
            counterparty.telegram_user_id,
            settlement_notification_text(
                settlement,
                recorder,
                counterparty_language,
            ),
        )
    except TelegramAPIError:
        # The settlement is authoritative; notification delivery is best effort.
        pass
