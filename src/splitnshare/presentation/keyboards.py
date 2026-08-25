from collections.abc import Sequence
from uuid import UUID

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup,
)

from splitnshare.application.dto import ExpenseDTO, ExpensePage, GuestDTO, PersonDTO

ADD_EXPENSE = "➕ Add expense"
TRANSACTIONS = "📋 Transactions"
PEOPLE = "👥 People"
CANCEL = "Cancel"
BACK = "Back"
ADD_MANUAL = "Add person by name"
ADD_RECENT = "Add recent person"
REMOVE_PARTICIPANT = "Remove participant"
DONE = "Done selecting"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=ADD_EXPENSE), KeyboardButton(text=TRANSACTIONS)],
            [KeyboardButton(text=PEOPLE)],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard(*, include_back: bool = True) -> ReplyKeyboardMarkup:
    buttons = [KeyboardButton(text=BACK)] if include_back else []
    buttons.append(KeyboardButton(text=CANCEL))
    return ReplyKeyboardMarkup(keyboard=[buttons], resize_keyboard=True)


def participant_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Choose Telegram users",
                    request_users=KeyboardButtonRequestUsers(
                        request_id=1001,
                        user_is_bot=False,
                        max_quantity=9,
                        request_name=True,
                        request_username=True,
                    ),
                )
            ],
            [KeyboardButton(text=ADD_MANUAL), KeyboardButton(text=ADD_RECENT)],
            [KeyboardButton(text=REMOVE_PARTICIPANT), KeyboardButton(text=DONE)],
            [KeyboardButton(text=BACK), KeyboardButton(text=CANCEL)],
        ],
        resize_keyboard=True,
    )


def split_method_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Split equally", callback_data="expense:split:equal"),
                InlineKeyboardButton(text="Exact amounts", callback_data="expense:split:exact"),
            ]
        ]
    )


def recent_people_keyboard(people: Sequence[PersonDTO]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=person.display_name,
                    callback_data=f"expense:addperson:{person.id}",
                )
            ]
            for person in people
        ]
    )


def remove_participant_keyboard(
    participants: Sequence[dict[str, str]], creator_id: str
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Remove {participant['name']}",
                    callback_data=f"expense:remove:{participant['id']}",
                )
            ]
            for participant in participants
            if participant["id"] != creator_id
        ]
    )


def expense_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Confirm", callback_data="expense:confirm")],
            [InlineKeyboardButton(text="Cancel", callback_data="expense:cancel")],
        ]
    )


def expense_list_keyboard(page: ExpensePage) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{item.description} · {item.total.format()}",
                callback_data=f"expense:view:{item.id}",
            )
        ]
        for item in page.items
    ]
    if page.next_cursor:
        rows.append(
            [InlineKeyboardButton(text="More", callback_data=f"expense:page:{page.next_cursor}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def expense_details_keyboard(expense: ExpenseDTO, viewer_id: UUID) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Back to transactions", callback_data="expense:list")]
    ]
    if expense.creator_person_id == viewer_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Delete", callback_data=f"expense:delete_ask:{expense.id}"
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_confirm_keyboard(expense_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Delete permanently from balances",
                    callback_data=f"expense:delete:{expense_id}",
                )
            ],
            [InlineKeyboardButton(text="Keep", callback_data=f"expense:view:{expense_id}")],
        ]
    )


def guests_keyboard(guests: list[GuestDTO] | tuple[GuestDTO, ...]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Transfer {guest.display_name}",
                    callback_data=f"guest:transfer:{guest.person_id}",
                )
            ]
            for guest in guests
        ]
    )


def transfer_target_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Choose registered user",
                    request_users=KeyboardButtonRequestUsers(
                        request_id=2001,
                        user_is_bot=False,
                        max_quantity=1,
                        request_name=True,
                        request_username=True,
                    ),
                )
            ],
            [KeyboardButton(text=CANCEL)],
        ],
        resize_keyboard=True,
    )


def transfer_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Transfer everything", callback_data="guest:confirm")],
            [InlineKeyboardButton(text="Cancel", callback_data="guest:cancel")],
        ]
    )
