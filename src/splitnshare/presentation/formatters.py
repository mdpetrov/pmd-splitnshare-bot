from collections.abc import Sequence
from html import escape
from uuid import UUID

from splitnshare.application.dto import BalanceDTO, ExpenseDTO, TransferPreviewDTO
from splitnshare.domain.enums import Language
from splitnshare.domain.money import Money
from splitnshare.presentation.datetimes import format_local_datetime
from splitnshare.presentation.i18n import translate
from splitnshare.presentation.labels import participant_html


def expense_text(
    expense: ExpenseDTO,
    language: Language = Language.ENGLISH,
    timezone: str = "UTC",
) -> str:
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
) -> str:
    items = [translate(language, "your_transactions")]
    for expense in expenses:
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
        items.append(
            translate(
                language,
                "transaction_list_item",
                date=escape(format_local_datetime(expense.occurred_at, timezone, language)),
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
        )
    return "\n\n".join(items)


def transfer_preview_text(
    preview: TransferPreviewDTO, language: Language = Language.ENGLISH
) -> str:
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
    if not balances:
        return "\n\n".join(
            (translate(language, "balances_title"), translate(language, "no_balances"))
        )

    user_owes = [balance for balance in balances if balance.net_minor < 0]
    user_is_owed = [balance for balance in balances if balance.net_minor > 0]
    sections = [translate(language, "balances_title")]
    if user_owes:
        sections.append(_balance_section(user_owes, translate(language, "you_owe")))
    if user_is_owed:
        sections.append(
            _balance_section(user_is_owed, translate(language, "you_are_owed"))
        )
    return "\n\n".join(sections)


def _balance_section(balances: Sequence[BalanceDTO], heading: str) -> str:
    items = "\n".join(
        f"• {participant_html(balance.other_name, balance.other_person_id, balance.username)} — "
        f"{Money(abs(balance.net_minor), balance.currency).format()}"
        for balance in balances
    )
    return f"{heading}:\n{items}"
