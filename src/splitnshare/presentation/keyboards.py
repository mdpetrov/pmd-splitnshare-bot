"""Build reply and inline keyboards for every Telegram interaction flow."""

from collections.abc import Collection, Sequence
from uuid import UUID

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup,
)

from splitnshare.application.dto import (
    ActivityPage,
    BalanceDTO,
    ExpenseActivityDTO,
    ExpenseDTO,
    ExpensePage,
    FriendDTO,
    GuestDTO,
)
from splitnshare.domain.enums import SELECTABLE_LANGUAGES, Language
from splitnshare.domain.money import Money
from splitnshare.presentation.callbacks import uuid_token
from splitnshare.presentation.datetimes import format_local_datetime_compact
from splitnshare.presentation.i18n import translate
from splitnshare.presentation.labels import friend_label, participant_label
from splitnshare.presentation.timezones import TIMEZONE_CHOICES

ADD_EXPENSE = "➕ Add expense"
ACTIVITY = "📋 Activity"
SETTINGS = "⚙️ Settings"
CANCEL = "Cancel"
BACK = "Back"
ADD_MANUAL = "Add person by name"
ADD_RECENT = "Add recent person"
REMOVE_PARTICIPANT = "Remove participant"
DONE = "Done selecting"


def main_menu(language: Language = Language.ENGLISH) -> ReplyKeyboardMarkup:
    """Build the persistent reply keyboard for top-level features."""
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
    """Build an inline copy of the top-level navigation menu."""
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
    """Build a single-button return path to the main menu."""
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


def balances_keyboard(
    balances: Sequence[BalanceDTO], language: Language
) -> InlineKeyboardMarkup:
    """Build one drill-down action per person with an outstanding balance."""
    rows: list[list[InlineKeyboardButton]] = []
    seen_people: set[UUID] = set()
    for balance in balances:
        if balance.other_person_id in seen_people:
            continue
        seen_people.add(balance.other_person_id)
        rows.append(
            [
                InlineKeyboardButton(
                    text=participant_label(
                        balance.other_name,
                        balance.other_person_id,
                        balance.username,
                    ),
                    callback_data=(
                        f"balance:person:{uuid_token(balance.other_person_id)}"
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=translate(language, "main_menu"), callback_data="menu:show"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def person_balance_keyboard(
    balances: Sequence[BalanceDTO], language: Language
) -> InlineKeyboardMarkup:
    """Build currency settlement and history actions for one counterparty."""
    if not balances:
        return back_to_main_menu_keyboard(language)
    other_person_id = balances[0].other_person_id
    rows = [
        [
            InlineKeyboardButton(
                text=translate(
                    language,
                    "settle_amount_button",
                    amount=Money(abs(balance.net_minor), balance.currency).format(),
                ),
                callback_data=(
                    f"settle:select:{balance.other_person_id}:{balance.currency}"
                ),
            )
        ]
        for balance in balances
    ]
    rows.extend(
        (
            [
                InlineKeyboardButton(
                    text=translate(language, "transaction_history"),
                    callback_data=f"balance:history:{uuid_token(other_person_id)}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back_to_balances"),
                    callback_data="menu:balances",
                )
            ],
        )
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settlement_amount_keyboard(
    amount: Money,
    language: Language,
    *,
    back_callback: str = "menu:balances",
) -> InlineKeyboardMarkup:
    """Offer full, partial, and cancellation choices for a settlement."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(
                        language,
                        "settle_full_amount",
                        amount=amount.format(),
                    ),
                    callback_data="settle:full",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "settle_partial"),
                    callback_data="settle:partial",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data=back_callback,
                ),
                InlineKeyboardButton(
                    text=translate(language, "cancel"),
                    callback_data="menu:show",
                ),
            ],
        ]
    )


def cancel_keyboard(
    language: Language = Language.ENGLISH, *, include_back: bool = True
) -> ReplyKeyboardMarkup:
    """Build flow navigation with Cancel and an optional Back button."""
    buttons = [KeyboardButton(text=translate(language, "back"))] if include_back else []
    buttons.append(KeyboardButton(text=translate(language, "cancel")))
    return ReplyKeyboardMarkup(keyboard=[buttons], resize_keyboard=True)


def participant_keyboard(language: Language = Language.ENGLISH) -> ReplyKeyboardMarkup:
    """Build participant-selection actions for a new expense."""
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
    """Offer equal or exact expense allocation strategies."""
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
    """Build expense participant buttons from the user's friends."""
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
    """Build removal actions for non-creator draft participants."""
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
    """Build final confirmation and cancellation actions for an expense."""
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
    page: ExpensePage,
    language: Language = Language.ENGLISH,
    timezone: str = "UTC",
) -> InlineKeyboardMarkup:
    """Build dated expense-detail links and cursor pagination controls."""
    rows = [
        [
            InlineKeyboardButton(
                text=" · ".join(
                    (
                        format_local_datetime_compact(
                            item.occurred_at, timezone, language
                        ),
                        _short_button_text(item.description),
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


def activity_list_keyboard(
    page: ActivityPage,
    language: Language = Language.ENGLISH,
    timezone: str = "UTC",
) -> InlineKeyboardMarkup:
    """Build expense links and pagination for heterogeneous activity."""
    rows = [
        [
            InlineKeyboardButton(
                text=" · ".join(
                    (
                        format_local_datetime_compact(
                            item.expense.occurred_at, timezone, language
                        ),
                        _short_button_text(item.expense.description),
                    )
                ),
                callback_data=f"expense:view:{item.expense.id}",
            )
        ]
        for item in page.items
        if isinstance(item, ExpenseActivityDTO)
    ]
    if page.next_cursor:
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate(language, "more"),
                    callback_data=f"activity:page:{page.next_cursor}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=translate(language, "main_menu"), callback_data="menu:show"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def person_history_keyboard(
    page: ExpensePage,
    other_person_id: UUID,
    language: Language = Language.ENGLISH,
    timezone: str = "UTC",
) -> InlineKeyboardMarkup:
    """Build compact shared-history links while preserving person context."""
    person_token = uuid_token(other_person_id)
    rows = [
        [
            InlineKeyboardButton(
                text=" · ".join(
                    (
                        format_local_datetime_compact(
                            item.occurred_at, timezone, language
                        ),
                        _short_button_text(item.description),
                    )
                ),
                callback_data=f"bhv:{person_token}:{uuid_token(item.id)}",
            )
        ]
        for item in page.items
    ]
    if page.next_cursor:
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate(language, "more"),
                    callback_data=(
                        f"bhp:{person_token}:{uuid_token(page.next_cursor)}"
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=translate(language, "back_to_person_balance"),
                callback_data=f"balance:person:{person_token}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def person_activity_keyboard(
    page: ActivityPage,
    other_person_id: UUID,
    language: Language = Language.ENGLISH,
    timezone: str = "UTC",
    origin: str = "balance",
) -> InlineKeyboardMarkup:
    """Build person activity with navigation back to its originating screen."""
    person_token = uuid_token(other_person_id)
    from_friend = origin == "friend"
    expense_prefix = "fhv" if from_friend else "bhv"
    page_prefix = "fa" if from_friend else "ba"
    rows = [
        [
            InlineKeyboardButton(
                text=" · ".join(
                    (
                        format_local_datetime_compact(
                            item.expense.occurred_at, timezone, language
                        ),
                        _short_button_text(item.expense.description),
                    )
                ),
                callback_data=(
                    f"{expense_prefix}:{person_token}:{uuid_token(item.expense.id)}"
                ),
            )
        ]
        for item in page.items
        if isinstance(item, ExpenseActivityDTO)
    ]
    if page.next_cursor:
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate(language, "more"),
                    callback_data=f"{page_prefix}:{person_token}:{page.next_cursor}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=translate(
                    language,
                    "back_to_friend" if from_friend else "back_to_person_balance",
                ),
                callback_data=(
                    f"friend:view:{other_person_id}"
                    if from_friend
                    else f"balance:person:{person_token}"
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _short_button_text(value: str, limit: int = 40) -> str:
    """Truncate long button labels while preserving a visible ellipsis."""
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def expense_date_keyboard(language: Language) -> InlineKeyboardMarkup:
    """Offer common transaction-time presets and custom date entry."""
    choices = (
        ("date_now", "now"),
        ("date_30_minutes_ago", "minus_30m"),
        ("date_1_hour_ago", "minus_1h"),
        ("date_2_hours_ago", "minus_2h"),
        ("date_3_hours_ago", "minus_3h"),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, label_key),
                    callback_data=f"expense:date:{callback_value}",
                )
                for label_key, callback_value in choices[:2]
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, label_key),
                    callback_data=f"expense:date:{callback_value}",
                )
                for label_key, callback_value in choices[2:4]
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, choices[4][0]),
                    callback_data=f"expense:date:{choices[4][1]}",
                ),
                InlineKeyboardButton(
                    text=translate(language, "date_custom"),
                    callback_data="expense:date:custom",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"),
                    callback_data="expense:date:back",
                ),
                InlineKeyboardButton(
                    text=translate(language, "cancel"),
                    callback_data="expense:cancel",
                ),
            ],
        ]
    )


def expense_details_keyboard(
    expense: ExpenseDTO,
    viewer_id: UUID,
    language: Language = Language.ENGLISH,
    *,
    back_callback: str = "expense:list",
    back_label_key: str = "back_transactions",
) -> InlineKeyboardMarkup:
    """Build expense navigation and creator-only deletion actions."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=translate(language, back_label_key), callback_data=back_callback
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
    """Build destructive expense-deletion confirmation controls."""
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
    """Build active guest actions, including suggested transfer targets."""
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
    """Build legacy registered-friend removal actions and back navigation."""
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
    """Build the unified friend list with detail and creation actions."""
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
    friend: FriendDTO,
    language: Language,
    transfer_guest: GuestDTO | None = None,
) -> InlineKeyboardMarkup:
    """Build friend actions, including owner-authorized guest transfer."""
    rows = [
        [
            InlineKeyboardButton(
                text=translate(language, "rename_friend"),
                callback_data=f"friend:rename:{friend.person_id}",
            ),
            InlineKeyboardButton(
                text=translate(language, "remove_friend_short"),
                callback_data=f"friend:remove_ask:d:{friend.person_id}",
            ),
        ]
    ]
    if transfer_guest is not None:
        target_id = transfer_guest.suggested_target_person_id
        target_name = transfer_guest.suggested_target_name
        has_suggestion = target_id is not None and target_name is not None
        target_label = ""
        if target_id is not None and target_name is not None:
            target_label = participant_label(
                target_name,
                target_id,
                transfer_guest.suggested_target_username,
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate(
                        language,
                        "transfer_friend_to" if has_suggestion else "transfer_friend",
                        name=target_label,
                    ),
                    callback_data=(
                        f"guest:transfer_hint:{transfer_guest.person_id}"
                        if has_suggestion
                        else f"guest:transfer:{transfer_guest.person_id}"
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=translate(language, "transaction_history"),
                callback_data=f"friend:history:{uuid_token(friend.person_id)}",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=translate(language, "back_friends"),
                callback_data="friends:show",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def friend_remove_confirm_keyboard(
    friend_person_id: UUID, origin: str, language: Language
) -> InlineKeyboardMarkup:
    """Build friend-removal confirmation with origin-aware navigation."""
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
    """Build the legacy categorized friends navigation menu."""
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
    """Build a single-button return path to the unified friends list."""
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
    """Offer Telegram sharing or manual naming when adding a friend."""
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
    """Request a registered Telegram user as a guest-transfer target."""
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
    """Build irreversible guest-transfer confirmation controls."""
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
    """Build navigation for currency, language, and timezone settings."""
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
    """Build localized buttons for every supported timezone choice."""
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
    """Offer common currencies and a custom ISO-code option."""
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
    """Offer currently selectable interface languages and settings navigation."""
    labels = {
        Language.ENGLISH: "English",
        Language.RUSSIAN: "Русский",
    }
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *[
                [
                    InlineKeyboardButton(
                        text=labels[choice],
                        callback_data=f"settings:set_language:{choice.value}",
                    )
                ]
                for choice in SELECTABLE_LANGUAGES
            ],
            [
                InlineKeyboardButton(
                    text=translate(language, "back"), callback_data="settings:show"
                )
            ],
        ]
    )
