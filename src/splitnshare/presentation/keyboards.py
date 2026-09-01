from collections.abc import Sequence
from uuid import UUID

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup,
)

from splitnshare.application.dto import ExpenseDTO, ExpensePage, FriendDTO, GuestDTO
from splitnshare.domain.enums import Language
from splitnshare.presentation.i18n import translate

ADD_EXPENSE = "➕ Add expense"
TRANSACTIONS = "📋 Transactions"
SETTINGS = "⚙️ Settings"
CANCEL = "Cancel"
BACK = "Back"
ADD_MANUAL = "Add person by name"
ADD_RECENT = "Add recent person"
REMOVE_PARTICIPANT = "Remove participant"
DONE = "Done selecting"


def main_menu(language: Language = Language.ENGLISH) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=translate(language, "add_expense")),
                KeyboardButton(text=translate(language, "transactions")),
            ],
            [
                KeyboardButton(text=translate(language, "balances")),
                KeyboardButton(text=translate(language, "friends")),
            ],
            [
                KeyboardButton(text=translate(language, "settings")),
            ],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard(
    language: Language = Language.ENGLISH, *, include_back: bool = True
) -> ReplyKeyboardMarkup:
    buttons = [KeyboardButton(text=translate(language, "back"))] if include_back else []
    buttons.append(KeyboardButton(text=translate(language, "cancel")))
    return ReplyKeyboardMarkup(keyboard=[buttons], resize_keyboard=True)


def participant_keyboard(language: Language = Language.ENGLISH) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=translate(language, "choose_telegram_users"),
                    request_users=KeyboardButtonRequestUsers(
                        request_id=1001,
                        user_is_bot=False,
                        max_quantity=9,
                        request_name=True,
                        request_username=True,
                    ),
                )
            ],
            [
                KeyboardButton(text=translate(language, "add_manual")),
                KeyboardButton(text=translate(language, "add_from_friends")),
            ],
            [
                KeyboardButton(text=translate(language, "remove_participant")),
                KeyboardButton(text=translate(language, "done")),
            ],
            [
                KeyboardButton(text=translate(language, "back")),
                KeyboardButton(text=translate(language, "cancel")),
            ],
        ],
        resize_keyboard=True,
    )


def split_method_keyboard(language: Language = Language.ENGLISH) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "split_equally"),
                    callback_data="expense:split:equal",
                ),
                InlineKeyboardButton(
                    text=translate(language, "exact_amounts"),
                    callback_data="expense:split:exact",
                ),
            ]
        ]
    )


def expense_friends_keyboard(friends: Sequence[FriendDTO]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=friend.display_name,
                    callback_data=f"expense:addfriend:{friend.person_id}",
                )
            ]
            for friend in friends
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


def expense_confirm_keyboard(language: Language = Language.ENGLISH) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "confirm"), callback_data="expense:confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "cancel"), callback_data="expense:cancel"
                )
            ],
        ]
    )


def expense_list_keyboard(
    page: ExpensePage, language: Language = Language.ENGLISH
) -> InlineKeyboardMarkup:
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
            [
                InlineKeyboardButton(
                    text=translate(language, "more"),
                    callback_data=f"expense:page:{page.next_cursor}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def expense_details_keyboard(
    expense: ExpenseDTO,
    viewer_id: UUID,
    language: Language = Language.ENGLISH,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=translate(language, "back_transactions"), callback_data="expense:list"
            )
        ]
    ]
    if expense.creator_person_id == viewer_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate(language, "delete"),
                    callback_data=f"expense:delete_ask:{expense.id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_confirm_keyboard(
    expense_id: UUID, language: Language = Language.ENGLISH
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "delete_from_balances"),
                    callback_data=f"expense:delete:{expense_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "keep"),
                    callback_data=f"expense:view:{expense_id}",
                )
            ],
        ]
    )


def guests_keyboard(
    guests: list[GuestDTO] | tuple[GuestDTO, ...],
    language: Language = Language.ENGLISH,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "transfer_guest", name=guest.display_name),
                    callback_data=f"guest:transfer:{guest.person_id}",
                )
            ]
            for guest in guests
        ]
        + [
            [
                InlineKeyboardButton(
                    text=translate(language, "back_friends"),
                    callback_data="friends:show",
                )
            ]
        ]
    )


def friends_menu_keyboard(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "registered_friends"),
                    callback_data="friends:registered",
                ),
                InlineKeyboardButton(
                    text=translate(language, "guests"), callback_data="friends:guests"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "add_friend"),
                    callback_data="friends:add",
                )
            ],
        ]
    )


def back_to_friends_keyboard(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "back_friends"),
                    callback_data="friends:show",
                )
            ]
        ]
    )


def add_friend_keyboard(language: Language) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=translate(language, "choose_friend_telegram"),
                    request_users=KeyboardButtonRequestUsers(
                        request_id=3001,
                        user_is_bot=False,
                        max_quantity=1,
                        request_name=True,
                        request_username=True,
                    ),
                )
            ],
            [KeyboardButton(text=translate(language, "add_named_guest"))],
            [
                KeyboardButton(text=translate(language, "back")),
                KeyboardButton(text=translate(language, "cancel")),
            ],
        ],
        resize_keyboard=True,
    )


def transfer_target_keyboard(language: Language = Language.ENGLISH) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=translate(language, "choose_registered"),
                    request_users=KeyboardButtonRequestUsers(
                        request_id=2001,
                        user_is_bot=False,
                        max_quantity=1,
                        request_name=True,
                        request_username=True,
                    ),
                )
            ],
            [KeyboardButton(text=translate(language, "cancel"))],
        ],
        resize_keyboard=True,
    )


def transfer_confirm_keyboard(language: Language = Language.ENGLISH) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "transfer_everything"),
                    callback_data="guest:confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "cancel"), callback_data="guest:cancel"
                )
            ],
        ]
    )


def settings_keyboard(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "currency"), callback_data="settings:currency"
                ),
                InlineKeyboardButton(
                    text=translate(language, "language"), callback_data="settings:language"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "main_menu"), callback_data="settings:close"
                )
            ],
        ]
    )


def currency_keyboard(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=code, callback_data=f"settings:set_currency:{code}")
                for code in ("USD", "EUR", "GBP")
            ],
            [
                InlineKeyboardButton(text=code, callback_data=f"settings:set_currency:{code}")
                for code in ("JPY", "RUB", "UAH")
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "other_currency"),
                    callback_data="settings:custom_currency",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"), callback_data="settings:show"
                )
            ],
        ]
    )


def language_keyboard(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="English", callback_data="settings:set_language:en"),
                InlineKeyboardButton(text="Русский", callback_data="settings:set_language:ru"),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"), callback_data="settings:show"
                )
            ],
        ]
    )
