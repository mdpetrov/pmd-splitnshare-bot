from html import escape

from splitnshare.application.dto import ExpenseDTO, TransferPreviewDTO
from splitnshare.domain.enums import Language
from splitnshare.domain.money import Money
from splitnshare.presentation.i18n import translate


def expense_text(
    expense: ExpenseDTO, language: Language = Language.ENGLISH
) -> str:
    shares = "\n".join(
        f"• {escape(split.display_name)}: "
        f"{Money(split.owed_minor, expense.total.currency).format()}"
        for split in expense.splits
    )
    return (
        f"<b>{escape(expense.description)}</b>\n"
        f"{translate(language, 'expense_total', total=expense.total.format())}\n"
        f"{translate(language, 'expense_paid_by', name=escape(expense.payer_name))}\n"
        f"{translate(language, 'expense_split', method=expense.split_method.value)}\n\n{shares}"
    )


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
                guest=escape(preview.guest_name),
                target=escape(preview.target_name),
            ),
            "",
            translate(language, "expenses_count", count=preview.expense_count),
            translate(language, "groups_count", count=preview.group_count),
            translate(
                language, "friendships_count", count=preview.friendship_count
            ),
            translate(language, "debt_amounts", amounts=debts),
            "",
            translate(language, "transfer_warning"),
        )
    )
