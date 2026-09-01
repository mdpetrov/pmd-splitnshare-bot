from collections.abc import Mapping

from splitnshare.domain.enums import Language

DEFAULT_LANGUAGE = Language.ENGLISH

_TEXTS: dict[Language, dict[str, str]] = {
    Language.ENGLISH: {
        "add_expense": "➕ Add expense",
        "transactions": "📋 Transactions",
        "people": "👥 People",
        "settings": "⚙️ Settings",
        "cancel": "Cancel",
        "back": "Back",
        "add_manual": "Add person by name",
        "add_recent": "Add recent person",
        "remove_participant": "Remove participant",
        "done": "Done selecting",
        "choose_telegram_users": "Choose Telegram users",
        "split_equally": "Split equally",
        "exact_amounts": "Exact amounts",
        "confirm": "Confirm",
        "more": "More",
        "back_transactions": "Back to transactions",
        "delete": "Delete",
        "delete_from_balances": "Delete from history and balances",
        "keep": "Keep",
        "transfer_guest": "Transfer {name}",
        "choose_registered": "Choose registered user",
        "transfer_everything": "Transfer everything",
        "welcome": "Welcome, {name}. Add an expense or review your transactions.",
        "cancelled": "Cancelled.",
        "settings_title": (
            "<b>Settings</b>\nDefault currency: <b>{currency}</b>\n"
            "Language: <b>{language}</b>\n\n"
            "The currency is used only when a new expense has no explicit currency."
        ),
        "choose_currency": "Choose your default currency or enter another ISO code.",
        "enter_currency": "Enter a three-letter currency code, for example CAD.",
        "currency_saved": "Default currency changed to <b>{currency}</b>.",
        "choose_language": "Choose the interface language.",
        "language_saved": "Language changed to English.",
        "other_currency": "Other currency",
        "english": "English",
        "russian": "Russian",
        "main_menu": "Main menu",
        "currency": "💱 Currency",
        "language": "🌐 Language",
        "invalid_currency": "Enter exactly three Latin letters, for example CAD.",
        "expense_for": "What is this expense for?",
        "back_main": "Back at the main menu.",
        "description_invalid": "Enter a description between 1 and 240 characters.",
        "enter_total": "Enter the total, for example 12.50 or 12.50 USD.",
        "add_people": (
            "Add up to nine other people. They may be registered users, Telegram guests, "
            "or named guests."
        ),
        "participants": "Participants:",
        "guest_name": "Enter the guest's display name.",
        "no_recent": "No recent co-participants yet.",
        "choose_recent": "Choose a recent person:",
        "draft_expired": "The expense draft expired.",
        "use_start": "Use /start first.",
        "person_unavailable": "That person is no longer available.",
        "participant_limit": "The ten-participant limit has been reached.",
        "continue_participants": "Continue selecting participants.",
        "enter_total_again": "Enter the total again.",
        "no_participants_remove": "There are no additional participants to remove.",
        "choose_remove": "Choose a participant to remove:",
        "payer_remove": "The payer cannot be removed.",
        "add_one_participant": "Add at least one other participant.",
        "split_how": "How should the total be split?",
        "owes_prompt": "How much does {name} owe? Enter 0 if the payer owes nothing.",
        "owes_next": "How much does {name} owe?",
        "split_again": "Choose the split again when ready.",
        "shares_mismatch": (
            "Those shares do not total {total}. Start again with {name}."
        ),
        "review": "Review <b>{description}</b>",
        "total": "Total: {total}",
        "paid_you": "Paid by: you",
        "expense_saved": "Expense saved.",
        "no_expenses": "You do not have any active expenses yet.",
        "no_active_expenses": "You do not have any active expenses.",
        "your_transactions": "Your transactions:",
        "delete_question": "Delete this expense from active history and balances?",
        "expense_deleted": "Expense deleted.",
        "expense_already_deleted": "Expense was already deleted.",
        "no_guests": "You have no active guests. Add a guest while creating an expense.",
        "guests_intro": "Your guests. A transfer moves all history and group memberships:",
        "choose_transfer_target": "Choose a user who has already started this bot.",
        "target_not_registered": (
            "That person has not started this bot. Ask them to register, then choose them again."
        ),
        "transfer_expired": "The transfer draft expired.",
        "transfer_completed": (
            "Transfer completed. {expenses} expense(s) and {groups} group membership(s) "
            "moved to {name}."
        ),
        "transfer_notification": (
            "A guest profile and all of its expense history were transferred to your account."
        ),
        "transfer_cancelled": "Transfer cancelled.",
        "expense_total": "Total: {total}",
        "expense_paid_by": "Paid by: {name}",
        "expense_split": "Split: {method}",
        "transfer_question": "Transfer <b>{guest}</b> to <b>{target}</b>?",
        "expenses_count": "Expenses: {count}",
        "groups_count": "Groups: {count}",
        "debt_amounts": "Recorded debt amounts: {amounts}",
        "none": "none",
        "transfer_warning": (
            "Everything will move atomically. This cannot be reversed in the bot."
        ),
    },
    Language.RUSSIAN: {
        "add_expense": "➕ Добавить расход",
        "transactions": "📋 Транзакции",
        "people": "👥 Люди",
        "settings": "⚙️ Настройки",
        "cancel": "Отмена",
        "back": "Назад",
        "add_manual": "Добавить человека по имени",
        "add_recent": "Добавить недавнего участника",
        "remove_participant": "Удалить участника",
        "done": "Закончить выбор",
        "choose_telegram_users": "Выбрать пользователей Telegram",
        "split_equally": "Разделить поровну",
        "exact_amounts": "Точные суммы",
        "confirm": "Подтвердить",
        "more": "Ещё",
        "back_transactions": "Назад к транзакциям",
        "delete": "Удалить",
        "delete_from_balances": "Удалить из истории и балансов",
        "keep": "Оставить",
        "transfer_guest": "Перенести {name}",
        "choose_registered": "Выбрать зарегистрированного пользователя",
        "transfer_everything": "Перенести всё",
        "welcome": "Добро пожаловать, {name}. Добавьте расход или откройте транзакции.",
        "cancelled": "Отменено.",
        "settings_title": (
            "<b>Настройки</b>\nВалюта по умолчанию: <b>{currency}</b>\n"
            "Язык: <b>{language}</b>\n\n"
            "Валюта используется только для новых расходов без явно указанной валюты."
        ),
        "choose_currency": "Выберите валюту по умолчанию или введите другой код ISO.",
        "enter_currency": "Введите трёхбуквенный код валюты, например CAD.",
        "currency_saved": "Валюта по умолчанию изменена на <b>{currency}</b>.",
        "choose_language": "Выберите язык интерфейса.",
        "language_saved": "Язык изменён на русский.",
        "other_currency": "Другая валюта",
        "english": "Английский",
        "russian": "Русский",
        "main_menu": "Главное меню",
        "currency": "💱 Валюта",
        "language": "🌐 Язык",
        "invalid_currency": "Введите ровно три латинские буквы, например CAD.",
        "expense_for": "На что был этот расход?",
        "back_main": "Вы вернулись в главное меню.",
        "description_invalid": "Введите описание длиной от 1 до 240 символов.",
        "enter_total": "Введите сумму, например 12.50 или 12.50 USD.",
        "add_people": (
            "Добавьте до девяти человек: зарегистрированных пользователей, гостей Telegram "
            "или гостей по имени."
        ),
        "participants": "Участники:",
        "guest_name": "Введите отображаемое имя гостя.",
        "no_recent": "Недавних соучастников пока нет.",
        "choose_recent": "Выберите недавнего участника:",
        "draft_expired": "Черновик расхода устарел.",
        "use_start": "Сначала используйте /start.",
        "person_unavailable": "Этот человек больше недоступен.",
        "participant_limit": "Достигнут лимит в десять участников.",
        "continue_participants": "Продолжите выбор участников.",
        "enter_total_again": "Введите сумму ещё раз.",
        "no_participants_remove": "Нет дополнительных участников для удаления.",
        "choose_remove": "Выберите участника для удаления:",
        "payer_remove": "Плательщика нельзя удалить.",
        "add_one_participant": "Добавьте хотя бы одного участника.",
        "split_how": "Как разделить сумму?",
        "owes_prompt": "Сколько должен(на) {name}? Введите 0, если плательщик ничего не должен.",
        "owes_next": "Сколько должен(на) {name}?",
        "split_again": "Когда будете готовы, снова выберите способ разделения.",
        "shares_mismatch": "Сумма долей не равна {total}. Начните снова с {name}.",
        "review": "Проверьте <b>{description}</b>",
        "total": "Сумма: {total}",
        "paid_you": "Оплатили вы",
        "expense_saved": "Расход сохранён.",
        "no_expenses": "У вас пока нет активных расходов.",
        "no_active_expenses": "У вас нет активных расходов.",
        "your_transactions": "Ваши транзакции:",
        "delete_question": "Удалить этот расход из активной истории и балансов?",
        "expense_deleted": "Расход удалён.",
        "expense_already_deleted": "Расход уже был удалён.",
        "no_guests": "У вас нет активных гостей. Добавьте гостя при создании расхода.",
        "guests_intro": "Ваши гости. Перенос перемещает всю историю и участие в группах:",
        "choose_transfer_target": "Выберите пользователя, который уже запускал этого бота.",
        "target_not_registered": (
            "Этот человек ещё не запускал бота. Попросите его зарегистрироваться и повторите."
        ),
        "transfer_expired": "Черновик переноса устарел.",
        "transfer_completed": (
            "Перенос завершён. Расходов перенесено: {expenses}; участий в группах: {groups}. "
            "Новый пользователь: {name}."
        ),
        "transfer_notification": (
            "Профиль гостя и вся история его расходов были перенесены в вашу учётную запись."
        ),
        "transfer_cancelled": "Перенос отменён.",
        "expense_total": "Сумма: {total}",
        "expense_paid_by": "Оплатил(а): {name}",
        "expense_split": "Разделение: {method}",
        "transfer_question": "Перенести <b>{guest}</b> к <b>{target}</b>?",
        "expenses_count": "Расходы: {count}",
        "groups_count": "Группы: {count}",
        "debt_amounts": "Учтённые суммы долгов: {amounts}",
        "none": "нет",
        "transfer_warning": "Всё будет перенесено атомарно. Отменить это в боте нельзя.",
    },
}


def translate(locale: Language | str, key: str, **values: object) -> str:
    try:
        selected = Language(locale)
    except ValueError:
        selected = DEFAULT_LANGUAGE
    template = _TEXTS.get(selected, _TEXTS[DEFAULT_LANGUAGE]).get(
        key, _TEXTS[DEFAULT_LANGUAGE][key]
    )
    return template.format(**values)


def button_values(key: str) -> set[str]:
    return {catalog[key] for catalog in _TEXTS.values()}


def language_name(language: Language, display_language: Language) -> str:
    key = "english" if language is Language.ENGLISH else "russian"
    return translate(display_language, key)


def catalogs() -> Mapping[Language, Mapping[str, str]]:
    return _TEXTS
