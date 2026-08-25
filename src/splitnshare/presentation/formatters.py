from html import escape

from splitnshare.application.dto import ExpenseDTO, TransferPreviewDTO
from splitnshare.domain.money import Money


def expense_text(expense: ExpenseDTO) -> str:
    shares = "\n".join(
        f"• {escape(split.display_name)}: "
        f"{Money(split.owed_minor, expense.total.currency).format()}"
        for split in expense.splits
    )
    return (
        f"<b>{escape(expense.description)}</b>\n"
        f"Total: {expense.total.format()}\n"
        f"Paid by: {escape(expense.payer_name)}\n"
        f"Split: {expense.split_method.value}\n\n{shares}"
    )


def transfer_preview_text(preview: TransferPreviewDTO) -> str:
    debts = ", ".join(
        Money(value, currency).format() for currency, value in sorted(preview.debt_totals.items())
    ) or "none"
    return (
        f"Transfer <b>{escape(preview.guest_name)}</b> to <b>{escape(preview.target_name)}</b>?\n\n"
        f"Expenses: {preview.expense_count}\n"
        f"Groups: {preview.group_count}\n"
        f"Recorded debt amounts: {debts}\n\n"
        "Everything will move atomically. This cannot be reversed in the bot."
    )
