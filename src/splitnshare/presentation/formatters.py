"""Render application DTOs as safe localized Telegram HTML messages."""

from collections import defaultdict
from collections.abc import Sequence
from html import escape
from uuid import UUID

from splitnshare.application.dto import (
    ActivityItemDTO,
    BalanceDTO,
    ExpenseActivityDTO,
    ExpenseDTO,
    PersonDTO,
    SettlementActivityDTO,
    SettlementDTO,
    TransferPreviewDTO,
    TransferResultDTO,
)
from splitnshare.domain.enums import Language
from splitnshare.domain.money import Money
from splitnshare.presentation.datetimes import format_local_date, format_local_datetime
from splitnshare.presentation.i18n import translate
from splitnshare.presentation.labels import participant_html


def welcome_text(
    display_name: str,
    balances: Sequence[BalanceDTO],
    language: Language = Language.ENGLISH,
) -> str:
    """Render a greeting with separate gross payable and receivable totals."""
    lines = [translate(language, "welcome", name=escape(display_name))]
    if not balances:
        lines.extend(("", translate(language, "welcome_no_balances")))
        return "\n".join(lines)

    owed: dict[str, int] = defaultdict(int)
    owing: dict[str, int] = defaultdict(int)
    for balance in balances:
        if balance.net_minor > 0:
            owed[balance.currency] += balance.net_minor
        elif balance.net_minor < 0:
            owing[balance.currency] += abs(balance.net_minor)
    lines.append("")
    if owing:
        lines.append(
            translate(
                language,
                "welcome_you_owe",
                amounts=_money_totals(owing),
            )
        )
    if owed:
        lines.append(
            translate(
                language,
                "welcome_you_are_owed",
                amounts=_money_totals(owed),
            )
        )
    return "\n".join(lines)


def _money_totals(totals: dict[str, int]) -> str:
    """Format currency-separated minor-unit totals in deterministic order."""
    return ", ".join(
        Money(total, currency).format()
        for currency, total in sorted(totals.items())
    )


def expense_text(
    expense: ExpenseDTO,
    language: Language = Language.ENGLISH,
    timezone: str = "UTC",
) -> str:
    """Render complete expense details with payer and participant shares."""
    payer = participant_html(
        expense.payer_name, expense.payer_person_id, expense.payer_username
    )
    shares = "\n".join(
        f"• {participant_html(split.display_name, split.person_id, split.username)}: "
        f"{Money(split.owed_minor, expense.total.currency).format()}"
        for split in expense.splits
    )
    occurred_at = format_local_datetime(expense.occurred_at, timezone, language)
    return (
        f"<b>{escape(expense.description)}</b>\n"
        f"{translate(language, 'expense_total', total=expense.total.format())}\n"
        f"{translate(language, 'expense_date', date=occurred_at)}\n"
        f"{translate(language, 'expense_paid_by', name=payer)}\n"
        f"{translate(language, 'expense_split', method=expense.split_method.value)}\n\n{shares}"
    )


def transactions_text(
    expenses: Sequence[ExpenseDTO],
    viewer_person_id: UUID,
    language: Language = Language.ENGLISH,
    timezone: str = "UTC",
    title: str | None = None,
) -> str:
    """Render expense-only activity for callers using the legacy interface."""
    return activity_text(
        tuple(ExpenseActivityDTO(expense) for expense in expenses),
        viewer_person_id,
        language,
        timezone,
        title,
    )


def activity_text(
    items: Sequence[ActivityItemDTO],
    viewer_person_id: UUID,
    language: Language = Language.ENGLISH,
    timezone: str = "UTC",
    title: str | None = None,
) -> str:
    """Render date-grouped expense and settlement cards for an activity page."""
    lines = [title or translate(language, "your_transactions")]
    current_date: str | None = None
    for item in items:
        if isinstance(item, ExpenseActivityDTO):
            occurred_at = item.expense.occurred_at
            card = _expense_activity_line(
                item.expense, viewer_person_id, language
            )
        else:
            occurred_at = item.settlement.occurred_at
            card = _settlement_activity_line(item, viewer_person_id, language)
        item_date = format_local_date(occurred_at, timezone, language)
        if item_date != current_date:
            lines.append(f"📅 <b>{escape(item_date)}</b>")
            current_date = item_date
        lines.append(card)
    return "\n\n".join(lines)


def _expense_activity_line(
    expense: ExpenseDTO,
    viewer_person_id: UUID,
    language: Language,
) -> str:
    """Render one compact expense card with its viewer-specific effect."""
    creator = (
        translate(language, "you")
        if expense.creator_person_id == viewer_person_id
        else participant_html(
            expense.creator_name,
            expense.creator_person_id,
            expense.creator_username,
        )
    )
    viewer_split = next(
        split for split in expense.splits if split.person_id == viewer_person_id
    )
    if expense.payer_person_id == viewer_person_id:
        relation_key = "transaction_you_are_owed"
        relation_amount = expense.total.minor - viewer_split.owed_minor
    else:
        relation_key = "transaction_you_owe"
        relation_amount = viewer_split.owed_minor
    return translate(
        language,
        "transaction_list_item",
        creator=creator,
        description=escape(expense.description),
        total=escape(expense.total.format()),
        relation=translate(
            language,
            relation_key,
            amount=escape(
                Money(relation_amount, expense.total.currency).format()
            ),
        ),
    )


def _settlement_activity_line(
    item: SettlementActivityDTO,
    viewer_person_id: UUID,
    language: Language,
) -> str:
    """Render one compact settlement card from the viewer's direction."""
    settlement = item.settlement
    if viewer_person_id == settlement.payer_person_id:
        relation_key = "activity_settlement_paid"
        counterparty = participant_html(
            item.recipient_name,
            settlement.recipient_person_id,
            item.recipient_username,
        )
    else:
        relation_key = "activity_settlement_received"
        counterparty = participant_html(
            item.payer_name,
            settlement.payer_person_id,
            item.payer_username,
        )
    recorder = (
        translate(language, "you")
        if viewer_person_id == settlement.recorded_by_person_id
        else participant_html(
            item.recorded_by_name,
            settlement.recorded_by_person_id,
            item.recorded_by_username,
        )
    )
    return translate(
        language,
        "activity_settlement_item",
        relation=translate(
            language,
            relation_key,
            name=counterparty,
            amount=escape(settlement.amount.format()),
        ),
        recorder=recorder,
    )


def settlement_notification_text(
    settlement: SettlementDTO,
    recorder: PersonDTO,
    language: Language = Language.ENGLISH,
) -> str:
    """Render a counterparty notification for a recorded settlement."""
    if settlement.recorded_by_person_id != recorder.id:
        raise ValueError("Settlement recorder does not match the supplied person.")
    if settlement.payer_person_id == recorder.id:
        key = "settlement_notification_recorder_paid"
    elif settlement.recipient_person_id == recorder.id:
        key = "settlement_notification_recorder_received"
    else:
        raise ValueError("Settlement recorder is not one of its participants.")
    recorder_label = participant_html(
        recorder.display_name,
        recorder.id,
        recorder.username,
    )
    return translate(
        language,
        key,
        recorder=recorder_label,
        amount=escape(settlement.amount.format()),
    )


def expense_notification_text(
    expense: ExpenseDTO,
    recipient_person_id: UUID,
    language: Language = Language.ENGLISH,
) -> str:
    """Render a creator notification with the recipient's financial effect."""
    if recipient_person_id == expense.creator_person_id:
        raise ValueError("The expense creator does not receive a notification.")
    recipient_split = next(
        (
            split
            for split in expense.splits
            if split.person_id == recipient_person_id
        ),
        None,
    )
    if recipient_split is None:
        raise ValueError("The notification recipient is not an expense participant.")
    if recipient_person_id == expense.payer_person_id:
        relation_key = "transaction_you_are_owed"
        relation_minor = expense.total.minor - recipient_split.owed_minor
    else:
        relation_key = "transaction_you_owe"
        relation_minor = recipient_split.owed_minor
    return translate(
        language,
        "expense_created_notification",
        creator=participant_html(
            expense.creator_name,
            expense.creator_person_id,
            expense.creator_username,
        ),
        description=escape(expense.description),
        relation=translate(
            language,
            relation_key,
            amount=escape(Money(relation_minor, expense.total.currency).format()),
        ),
    )


def transfer_notification_text(
    result: TransferResultDTO,
    language: Language = Language.ENGLISH,
) -> str:
    """Render who transferred history and its active expense totals."""
    amounts = _money_totals(result.expense_totals) or translate(language, "none")
    return translate(
        language,
        "transfer_notification",
        initiator=participant_html(
            result.initiator_name,
            result.initiator_person_id,
            result.initiator_username,
        ),
        count=result.affected_counts["expenses"],
        amounts=amounts,
    )


def transfer_preview_text(
    preview: TransferPreviewDTO, language: Language = Language.ENGLISH
) -> str:
    """Render the scope and warning for an explicit guest transfer."""
    debts = ", ".join(
        Money(value, currency).format() for currency, value in sorted(preview.debt_totals.items())
    ) or translate(language, "none")
    return "\n".join(
        (
            translate(
                language,
                "transfer_question",
                guest=participant_html(
                    preview.guest_name,
                    preview.guest_person_id,
                    preview.guest_username,
                ),
                target=participant_html(
                    preview.target_name,
                    preview.target_person_id,
                    preview.target_username,
                ),
            ),
            "",
            translate(language, "expenses_count", count=preview.expense_count),
            translate(language, "groups_count", count=preview.group_count),
            translate(
                language, "friendships_count", count=preview.friendship_count
            ),
            translate(language, "settlements_count", count=preview.settlement_count),
            translate(language, "debt_amounts", amounts=debts),
            "",
            translate(language, "transfer_warning"),
        )
    )


def balances_text(
    balances: Sequence[BalanceDTO], language: Language = Language.ENGLISH
) -> str:
    """Render balances grouped by money owed and money receivable."""
    if not balances:
        return "\n\n".join(
            (translate(language, "balances_title"), translate(language, "no_balances"))
        )

    user_owes = [balance for balance in balances if balance.net_minor < 0]
    user_is_owed = [balance for balance in balances if balance.net_minor > 0]
    sections = [translate(language, "balances_title")]
    if user_owes:
        sections.append(
            _balance_section(user_owes, translate(language, "you_owe"), "🔴 ▼")
        )
    if user_is_owed:
        sections.append(
            _balance_section(
                user_is_owed, translate(language, "you_are_owed"), "🟢 ▲"
            )
        )
    return "\n\n".join(sections)


def person_balances_text(
    balances: Sequence[BalanceDTO], language: Language = Language.ENGLISH
) -> str:
    """Render every currency balance belonging to one counterparty."""
    if not balances:
        return translate(language, "no_balances")
    first = balances[0]
    title = translate(
        language,
        "balance_with",
        name=participant_html(first.other_name, first.other_person_id, first.username),
    )
    lines = [title]
    for balance in balances:
        relation_key = (
            "balance_you_owe_amount"
            if balance.net_minor < 0
            else "balance_you_are_owed_amount"
        )
        lines.append(
            "• "
            + translate(
                language,
                relation_key,
                amount=Money(abs(balance.net_minor), balance.currency).format(),
            )
        )
    return "\n".join(lines)


def _balance_section(
    balances: Sequence[BalanceDTO], heading: str, direction_marker: str
) -> str:
    """Render one direction of a balance list under a heading."""
    items = "\n".join(
        f"• {direction_marker} "
        f"{participant_html(balance.other_name, balance.other_person_id, balance.username)} — "
        f"{Money(abs(balance.net_minor), balance.currency).format()}"
        for balance in balances
    )
    return f"{heading}:\n{items}"
