from collections.abc import Collection, Sequence
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
from splitnshare.presentation.labels import friend_label, participant_label
from splitnshare.presentation.timezones import TIMEZONE_CHOICES

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


def main_menu_inline_keyboard(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "add_expense"),
                    callback_data="menu:add_expense",
                ),
                InlineKeyboardButton(
                    text=translate(language, "transactions"),
                    callback_data="menu:transactions",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "balances"),
                    callback_data="menu:balances",
                ),
                InlineKeyboardButton(
                    text=translate(language, "friends"),
                    callback_data="menu:friends",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "settings"),
                    callback_data="menu:settings",
                )
            ],
        ]
    )


def back_to_main_menu_keyboard(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "main_menu"),
                    callback_data="menu:show",
                )
            ]
        ]
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
                    text=friend_label(friend),
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
                text=" · ".join(
                    (
                        item.description,
                        item.total.format(),
                        participant_label(
                            item.payer_name,
                            item.payer_person_id,
                            item.payer_username,
                        ),
                    )
                ),
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
    rows.append(
        [
            InlineKeyboardButton(
                text=translate(language, "main_menu"),
                callback_data="menu:show",
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
    removable_person_ids: Collection[UUID] = (),
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for guest in guests:
        guest_label = participant_label(
            guest.display_name, guest.person_id, guest.username
        )
        target_id = guest.suggested_target_person_id
        target_name = guest.suggested_target_name
        has_suggestion = target_id is not None and target_name is not None
        if target_id is not None and target_name is not None:
            target_label = participant_label(
                target_name,
                target_id,
                guest.suggested_target_username,
            )
            rows.append(
                [
                    InlineKeyboardButton(
                        text=translate(
                            language,
                            "review_suggested_transfer",
                            guest=guest_label,
                            target=target_label,
                        ),
                        callback_data=f"guest:transfer_hint:{guest.person_id}",
                    )
                ]
            )
        row = [
            InlineKeyboardButton(
                text=(
                    translate(
                        language,
                        "choose_other_transfer_target",
                        guest=guest_label,
                    )
                    if has_suggestion
                    else translate(language, "transfer_guest", name=guest_label)
                ),
                callback_data=f"guest:transfer:{guest.person_id}",
            )
        ]
        if guest.person_id in removable_person_ids:
            row.append(
                InlineKeyboardButton(
                    text=translate(language, "remove_friend_short"),
                    callback_data=f"friend:remove_ask:g:{guest.person_id}",
                )
            )
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(
                text=translate(language, "back_friends"),
                callback_data="friends:show",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=translate(language, "main_menu"),
                callback_data="menu:show",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def registered_friends_keyboard(
    friends: Sequence[FriendDTO], language: Language
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=translate(
                    language,
                    "remove_friend",
                    name=friend_label(friend),
                ),
                callback_data=f"friend:remove_ask:r:{friend.person_id}",
            )
        ]
        for friend in friends
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=translate(language, "back_friends"),
                callback_data="friends:show",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def friends_list_keyboard(
    friends: Sequence[FriendDTO], language: Language
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=friend_label(friend),
                callback_data=f"friend:view:{friend.person_id}",
            )
        ]
        for friend in friends
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=translate(language, "add_friend"),
                callback_data="friends:add",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=translate(language, "main_menu"),
                callback_data="menu:show",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def friend_detail_keyboard(
    friend: FriendDTO, language: Language
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "rename_friend"),
                    callback_data=f"friend:rename:{friend.person_id}",
                ),
                InlineKeyboardButton(
                    text=translate(language, "remove_friend_short"),
                    callback_data=f"friend:remove_ask:d:{friend.person_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_friends"),
                    callback_data="friends:show",
                )
            ],
        ]
    )


def friend_remove_confirm_keyboard(
    friend_person_id: UUID, origin: str, language: Language
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "confirm_remove_friend"),
                    callback_data=f"friend:remove:{origin}:{friend_person_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "keep_friend"),
                    callback_data=(
                        f"friend:view:{friend_person_id}"
                        if origin == "d"
                        else "friends:registered"
                        if origin == "r"
                        else "friends:guests"
                    ),
                )
            ],
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
                    text=translate(language, "timezone"),
                    callback_data="settings:timezone",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "main_menu"), callback_data="menu:show"
                )
            ],
        ]
    )


def timezone_keyboard(
    language: Language, *, include_back: bool = True
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=translate(language, choice.label_key),
                callback_data=f"settings:set_timezone:{choice.callback_key}",
            )
        ]
        for choice in TIMEZONE_CHOICES
    ]
    if include_back:
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data="settings:show",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
