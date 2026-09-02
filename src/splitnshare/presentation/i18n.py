"""Store interface translations and resolve localized text by message key."""

from collections.abc import Mapping

from splitnshare.domain.enums import Language

DEFAULT_LANGUAGE = Language.ENGLISH

_TEXTS: dict[Language, dict[str, str]] = {
    Language.ENGLISH: {
        "add_expense": "➕ Add expense",
        "transactions": "📋 Activity",
        "balances": "💰 Balances",
        "friends": "👥 Friends",
        "settings": "⚙️ Settings",
        "cancel": "Cancel",
        "back": "Back",
        "add_manual": "Add person by name",
        "add_from_friends": "Add from friends",
        "remove_participant": "Remove participant",
        "done": "Done selecting",
        "choose_telegram_users": "Choose Telegram users",
        "split_equally": "Split equally",
        "exact_amounts": "Exact amounts",
        "confirm": "Confirm",
        "more": "More",
        "back_transactions": "Back to activity",
        "delete": "Delete",
        "delete_from_balances": "Delete from history and balances",
        "keep": "Keep",
        "transfer_guest": "Transfer {name}",
        "choose_registered": "Choose registered user",
        "transfer_everything": "Transfer everything",
        "welcome": "Hi, {name}!",
        "welcome_you_owe": "🔴 ▼ You owe: <b>{amounts}</b>",
        "welcome_you_are_owed": "🟢 ▲ You are owed: <b>{amounts}</b>",
        "welcome_no_balances": "You have no outstanding balances.",
        "cancelled": "Cancelled.",
        "settings_title": (
            "<b>Settings</b>\nDefault currency: <b>{currency}</b>\n"
            "Language: <b>{language}</b>\nTimezone: <b>{timezone}</b>\n\n"
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
        "main_menu_prompt": "<b>Main menu</b>\nChoose what you want to do.",
        "currency": "💱 Currency",
        "language": "🌐 Language",
        "timezone": "🕒 Timezone",
        "choose_timezone": (
            "<b>Choose your timezone</b>\n\n"
            "The UTC offsets are familiar reference offsets. The bot stores the city-based "
            "timezone, so daylight-saving changes are applied automatically where relevant."
        ),
        "timezone_saved": "Timezone changed to <b>{timezone}</b>.",
        "timezone_not_selected": "not selected",
        "timezone_invalid": "That timezone option is no longer available. Choose again.",
        "onboarding_welcome": (
            "Welcome, {name}. Before opening the main menu, choose your timezone.\n\n"
            "Your default currency is <b>{currency}</b> and your interface language is "
            "<b>{language}</b>. Currency and language can be changed later in Settings."
        ),
        "onboarding_timezone_required": (
            "Please choose your timezone before continuing to the main menu."
        ),
        "onboarding_complete": (
            "Setup complete. You can change timezone, currency, and language in Settings."
        ),
        "timezone_los_angeles": "UTC-8 (Los Angeles, Vancouver)",
        "timezone_new_york": "UTC-5 (New York, Toronto)",
        "timezone_utc": "UTC+0 (UTC, Reykjavik)",
        "timezone_london": "UTC+0 (London, Lisbon)",
        "timezone_madrid": "UTC+1 (Madrid, Paris, Berlin)",
        "timezone_athens": "UTC+2 (Athens, Kyiv)",
        "timezone_moscow": "UTC+3 (Moscow, Istanbul)",
        "timezone_dubai": "UTC+4 (Dubai, Baku)",
        "timezone_kolkata": "UTC+5:30 (Delhi, Mumbai)",
        "timezone_bangkok": "UTC+7 (Bangkok, Jakarta)",
        "timezone_singapore": "UTC+8 (Singapore, Beijing)",
        "timezone_tokyo": "UTC+9 (Tokyo, Seoul)",
        "timezone_sydney": "UTC+10 (Sydney, Melbourne)",
        "invalid_currency": "Enter exactly three Latin letters, for example CAD.",
        "expense_for": "What is this expense for?",
        "back_main": "Back at the main menu.",
        "description_invalid": "Enter a description between 1 and 240 characters.",
        "enter_total": "Enter the total, for example 12.50 or 12.50 USD.",
        "choose_expense_date": "When did this expense happen?",
        "date_now": "Now",
        "date_30_minutes_ago": "30 min ago",
        "date_1_hour_ago": "1 hour ago",
        "date_2_hours_ago": "2 hours ago",
        "date_3_hours_ago": "3 hours ago",
        "date_custom": "Custom",
        "date_selected": "Expense time: <b>{date}</b>.",
        "enter_custom_date": (
            "Enter the local date and time as <code>DD.MM.YYYY HH:MM</code> or "
            "<code>YYYY-MM-DD HH:MM</code>. You may omit the year: "
            "<code>DD.MM HH:MM</code>.\nTimezone: <b>{timezone}</b>."
        ),
        "invalid_custom_date": (
            "Enter a valid local date and time, for example "
            "<code>02.09.2026 18:30</code>."
        ),
        "expense_date": "Date: {date}",
        "add_people": "Add up to nine registered or unregistered friends.",
        "participants": "Participants:",
        "guest_name": "Enter the friend's display name.",
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
        "expense_created_notification": (
            "{creator} has just created an expense “{description}”. {relation}"
        ),
        "no_expenses": "You do not have any activity yet.",
        "no_active_expenses": "You do not have any activity.",
        "your_transactions": "Your activity:",
        "you": "You",
        "transaction_list_item": (
            "• {date}: {creator} added “{description}” for <b>{total}</b>. {relation}"
        ),
        "transaction_you_owe": "🔴 ▼ You owe <b>{amount}</b>.",
        "transaction_you_are_owed": "🟢 ▲ You are owed <b>{amount}</b>.",
        "activity_settlement_item": (
            "• {date}: <b>Settlement</b>. {relation} Recorded by {recorder}."
        ),
        "activity_settlement_paid": "🔴 ▼ You paid {name} <b>{amount}</b>.",
        "activity_settlement_received": "🟢 ▲ {name} paid you <b>{amount}</b>.",
        "balances_title": "<b>Balances</b>",
        "you_owe": "<b>You owe</b>",
        "you_are_owed": "<b>You are owed</b>",
        "no_balances": "You have no outstanding balances.",
        "balance_with": "<b>Balance with {name}</b>",
        "balance_you_owe_amount": "🔴 ▼ You owe <b>{amount}</b>",
        "balance_you_are_owed_amount": "🟢 ▲ You are owed <b>{amount}</b>",
        "balance_person_stale": "That balance is no longer available.",
        "settle_amount_button": "Settle · {amount}",
        "transaction_history": "Activity history",
        "transactions_with": "<b>Activity with {name}</b>",
        "no_transactions_with_person": "There is no activity with this person.",
        "back_to_person_balance": "Back to person balance",
        "back_to_balances": "Back to balances",
        "settle_balance_button": "Settle {name} · {amount}",
        "settle_you_pay": (
            "You owe <b>{name}</b> <b>{amount}</b>. Record a payment?"
        ),
        "settle_other_pays": (
            "<b>{name}</b> owes you <b>{amount}</b>. Record that they paid you?"
        ),
        "settle_full_amount": "Settle all · {amount}",
        "settle_partial": "Enter partial amount",
        "settle_enter_amount": "Enter the amount paid in {currency}.",
        "settle_wrong_currency": "Enter an amount in {currency}.",
        "settle_invalid_amount": (
            "Enter a positive amount no greater than the outstanding {amount}."
        ),
        "settlement_saved": "Payment of <b>{amount}</b> recorded.",
        "settlement_stale": (
            "That balance changed or is no longer available. Open Balances and try again."
        ),
        "delete_question": "Delete this expense from active history and balances?",
        "expense_deleted": "Expense deleted.",
        "expense_already_deleted": "Expense was already deleted.",
        "no_guests": "You have no active guests. Add a guest while creating an expense.",
        "guests_intro": "<b>Your active guests</b>",
        "transfer_explanation": (
            "An unregistered friend uses a temporary participant profile. A Telegram-linked "
            "profile transfers automatically when that account registers. Transfer history "
            "is also available for manual profiles or as a fallback: it replaces the profile "
            "with one registered user across every expense, balance, friendship, and group "
            "membership. It does not send money or merge groups, requires confirmation, and "
            "cannot currently be reversed."
        ),
        "registration_suggestion": (
            "↳ Telegram account is registered as {target}. Review this remaining profile "
            "if its automatic transfer was not completed."
        ),
        "review_suggested_transfer": "Review {guest} → {target}",
        "choose_other_transfer_target": "Choose another user for {guest}",
        "registration_suggestion_unavailable": (
            "That registration suggestion is no longer available. Refresh Guests and try again."
        ),
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
            "{initiator} transferred <b>{count}</b> transactions to your account with a "
            "total of <b>{amounts}</b>."
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
        "friendships_count": "Friend-list entries: {count}",
        "settlements_count": "Recorded payments: {count}",
        "friends_title": (
            "<b>Friends</b>\nRegistered friends: <b>{registered}</b>\n"
            "Active guests: <b>{guests}</b>"
        ),
        "friends_list_title": "<b>Friends</b>\nChoose a friend to view available actions.",
        "friend_details": "<b>{name}</b>\nStatus: {status}",
        "friend_transaction_count": "Shared transactions: <b>{count}</b>",
        "friend_total_balance": "<b>Total balance</b>",
        "friend_no_balance": "You are settled up.",
        "friend_registered": "registered",
        "friend_unregistered": "not registered",
        "rename_friend": "Rename",
        "transfer_friend": "Transfer history",
        "transfer_friend_to": "Transfer history to {name}",
        "rename_friend_prompt": "Enter a new private name for this friend.",
        "friend_renamed": "Friend renamed to {name}.",
        "registered_friends": "Registered friends",
        "guests": "Guests",
        "add_friend": "Add friend",
        "no_registered_friends": "You have no registered friends yet.",
        "registered_friends_intro": "Your registered friends:",
        "choose_friend": "Choose a friend:",
        "no_friends": "Your Friends list is empty.",
        "add_friend_prompt": "Choose a Telegram user or create a friend by name.",
        "choose_friend_telegram": "Choose a Telegram user",
        "add_named_guest": "Add friend by name",
        "friend_name": "Enter the friend's display name.",
        "friend_added": "{name} is now in your Friends list.",
        "remove_friend": "Remove {name}",
        "remove_friend_short": "Remove",
        "remove_friend_question": "Remove <b>{name}</b> from Friends?",
        "remove_friend_warning": (
            "Existing expenses and balances will remain. Adding another expense with this "
            "person will add them to Friends again."
        ),
        "confirm_remove_friend": "Remove from Friends",
        "keep_friend": "Keep friend",
        "friend_removed": "{name} was removed from Friends.",
        "friend_already_removed": "That person is no longer in Friends.",
        "back_friends": "Back to Friends",
    },
    Language.RUSSIAN: {
        "add_expense": "➕ Добавить расход",
        "transactions": "📋 Активность",
        "balances": "💰 Балансы",
        "friends": "👥 Друзья",
        "settings": "⚙️ Настройки",
        "cancel": "Отмена",
        "back": "Назад",
        "add_manual": "Добавить человека по имени",
        "add_from_friends": "Добавить из друзей",
        "remove_participant": "Удалить участника",
        "done": "Закончить выбор",
        "choose_telegram_users": "Выбрать пользователей Telegram",
        "split_equally": "Разделить поровну",
        "exact_amounts": "Точные суммы",
        "confirm": "Подтвердить",
        "more": "Ещё",
        "back_transactions": "Назад к активности",
        "delete": "Удалить",
        "delete_from_balances": "Удалить из истории и балансов",
        "keep": "Оставить",
        "transfer_guest": "Перенести {name}",
        "choose_registered": "Выбрать зарегистрированного пользователя",
        "transfer_everything": "Перенести всё",
        "welcome": "Привет, {name}!",
        "welcome_you_owe": "🔴 ▼ Вы должны: <b>{amounts}</b>",
        "welcome_you_are_owed": "🟢 ▲ Вам должны: <b>{amounts}</b>",
        "welcome_no_balances": "У вас нет непогашенных долгов.",
        "cancelled": "Отменено.",
        "settings_title": (
            "<b>Настройки</b>\nВалюта по умолчанию: <b>{currency}</b>\n"
            "Язык: <b>{language}</b>\nЧасовой пояс: <b>{timezone}</b>\n\n"
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
        "main_menu_prompt": "<b>Главное меню</b>\nВыберите действие.",
        "currency": "💱 Валюта",
        "language": "🌐 Язык",
        "timezone": "🕒 Часовой пояс",
        "choose_timezone": (
            "<b>Выберите часовой пояс</b>\n\n"
            "Смещения UTC указаны как привычный ориентир. Бот сохраняет городской часовой "
            "пояс, поэтому переходы на летнее время учитываются автоматически, где применимо."
        ),
        "timezone_saved": "Часовой пояс изменён на <b>{timezone}</b>.",
        "timezone_not_selected": "не выбран",
        "timezone_invalid": "Этот вариант часового пояса больше недоступен. Выберите снова.",
        "onboarding_welcome": (
            "Добро пожаловать, {name}. Перед открытием главного меню выберите часовой пояс.\n\n"
            "Валюта по умолчанию — <b>{currency}</b>, язык интерфейса — <b>{language}</b>. "
            "Валюту и язык позже можно изменить в Настройках."
        ),
        "onboarding_timezone_required": (
            "Выберите часовой пояс, чтобы продолжить и открыть главное меню."
        ),
        "onboarding_complete": (
            "Настройка завершена. Часовой пояс, валюту и язык можно изменить в Настройках."
        ),
        "timezone_los_angeles": "UTC-8 (Лос-Анджелес, Ванкувер)",
        "timezone_new_york": "UTC-5 (Нью-Йорк, Торонто)",
        "timezone_utc": "UTC+0 (UTC, Рейкьявик)",
        "timezone_london": "UTC+0 (Лондон, Лиссабон)",
        "timezone_madrid": "UTC+1 (Мадрид, Париж, Берлин)",
        "timezone_athens": "UTC+2 (Афины, Киев)",
        "timezone_moscow": "UTC+3 (Москва, Стамбул)",
        "timezone_dubai": "UTC+4 (Дубай, Баку)",
        "timezone_kolkata": "UTC+5:30 (Дели, Мумбаи)",
        "timezone_bangkok": "UTC+7 (Бангкок, Джакарта)",
        "timezone_singapore": "UTC+8 (Сингапур, Пекин)",
        "timezone_tokyo": "UTC+9 (Токио, Сеул)",
        "timezone_sydney": "UTC+10 (Сидней, Мельбурн)",
        "invalid_currency": "Введите ровно три латинские буквы, например CAD.",
        "expense_for": "На что был этот расход?",
        "back_main": "Вы вернулись в главное меню.",
        "description_invalid": "Введите описание длиной от 1 до 240 символов.",
        "enter_total": "Введите сумму, например 12.50 или 12.50 USD.",
        "choose_expense_date": "Когда произошёл этот расход?",
        "date_now": "Сейчас",
        "date_30_minutes_ago": "30 минут назад",
        "date_1_hour_ago": "1 час назад",
        "date_2_hours_ago": "2 часа назад",
        "date_3_hours_ago": "3 часа назад",
        "date_custom": "Другая дата",
        "date_selected": "Время расхода: <b>{date}</b>.",
        "enter_custom_date": (
            "Введите местные дату и время в формате <code>ДД.ММ.ГГГГ ЧЧ:ММ</code> "
            "или <code>ГГГГ-ММ-ДД ЧЧ:ММ</code>. Год можно не указывать: "
            "<code>ДД.ММ ЧЧ:ММ</code>.\nЧасовой пояс: <b>{timezone}</b>."
        ),
        "invalid_custom_date": (
            "Введите корректные местные дату и время, например "
            "<code>02.09.2026 18:30</code>."
        ),
        "expense_date": "Дата: {date}",
        "add_people": "Добавьте до девяти зарегистрированных или незарегистрированных друзей.",
        "participants": "Участники:",
        "guest_name": "Введите отображаемое имя друга.",
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
        "expense_created_notification": (
            "{creator} только что добавил(а) расход «{description}». {relation}"
        ),
        "no_expenses": "У вас пока нет активности.",
        "no_active_expenses": "У вас нет активности.",
        "your_transactions": "Ваша активность:",
        "you": "Вы",
        "transaction_list_item": (
            "• {date}: {creator} добавил(а) транзакцию «{description}» на сумму "
            "<b>{total}</b>. {relation}"
        ),
        "transaction_you_owe": "🔴 ▼ Вы должны <b>{amount}</b>.",
        "transaction_you_are_owed": "🟢 ▲ Вам должны <b>{amount}</b>.",
        "activity_settlement_item": (
            "• {date}: <b>Расчёт</b>. {relation} Записал(а): {recorder}."
        ),
        "activity_settlement_paid": "🔴 ▼ Вы заплатили {name} <b>{amount}</b>.",
        "activity_settlement_received": "🟢 ▲ {name} заплатил(а) вам <b>{amount}</b>.",
        "balances_title": "<b>Балансы</b>",
        "you_owe": "<b>Вы должны</b>",
        "you_are_owed": "<b>Вам должны</b>",
        "no_balances": "У вас нет непогашенных долгов.",
        "balance_with": "<b>Баланс с {name}</b>",
        "balance_you_owe_amount": "🔴 ▼ Вы должны <b>{amount}</b>",
        "balance_you_are_owed_amount": "🟢 ▲ Вам должны <b>{amount}</b>",
        "balance_person_stale": "Этот баланс больше недоступен.",
        "settle_amount_button": "Закрыть · {amount}",
        "transaction_history": "История активности",
        "transactions_with": "<b>Активность с {name}</b>",
        "no_transactions_with_person": "С этим человеком нет активности.",
        "back_to_person_balance": "Назад к балансу с человеком",
        "back_to_balances": "Назад к балансам",
        "settle_balance_button": "Закрыть долг: {name} · {amount}",
        "settle_you_pay": (
            "Вы должны <b>{name}</b> <b>{amount}</b>. Записать платёж?"
        ),
        "settle_other_pays": (
            "<b>{name}</b> должен(на) вам <b>{amount}</b>. Записать полученный платёж?"
        ),
        "settle_full_amount": "Закрыть полностью · {amount}",
        "settle_partial": "Ввести часть суммы",
        "settle_enter_amount": "Введите выплаченную сумму в {currency}.",
        "settle_wrong_currency": "Введите сумму в валюте {currency}.",
        "settle_invalid_amount": (
            "Введите положительную сумму не больше остатка {amount}."
        ),
        "settlement_saved": "Платёж <b>{amount}</b> записан.",
        "settlement_stale": (
            "Баланс изменился или больше недоступен. Откройте Балансы и повторите."
        ),
        "delete_question": "Удалить этот расход из активной истории и балансов?",
        "expense_deleted": "Расход удалён.",
        "expense_already_deleted": "Расход уже был удалён.",
        "no_guests": "У вас нет активных гостей. Добавьте гостя при создании расхода.",
        "guests_intro": "<b>Ваши активные гости</b>",
        "transfer_explanation": (
            "Для незарегистрированного друга используется временный профиль участника. "
            "Профиль, связанный с Telegram, переносится автоматически, когда этот аккаунт "
            "регистрируется. Перенос истории также доступен для профиля, созданного вручную, "
            "или как запасной вариант: он заменяет профиль одним зарегистрированным "
            "пользователем во всех расходах, балансах, списках друзей и группах. Перенос не "
            "отправляет деньги и не объединяет группы; его нужно подтвердить, и сейчас его "
            "нельзя отменить."
        ),
        "registration_suggestion": (
            "↳ Аккаунт Telegram зарегистрирован как {target}. Проверьте оставшийся профиль, "
            "если автоматический перенос не завершился."
        ),
        "review_suggested_transfer": "Проверить {guest} → {target}",
        "choose_other_transfer_target": "Выбрать другого пользователя для {guest}",
        "registration_suggestion_unavailable": (
            "Эта подсказка больше недоступна. Обновите список гостей и повторите."
        ),
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
            "{initiator} перенёс(ла) <b>{count}</b> транзакций в вашу учётную запись "
            "на общую сумму <b>{amounts}</b>."
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
        "friendships_count": "Записи в списках друзей: {count}",
        "settlements_count": "Записанные платежи: {count}",
        "friends_title": (
            "<b>Друзья</b>\nЗарегистрированные друзья: <b>{registered}</b>\n"
            "Активные гости: <b>{guests}</b>"
        ),
        "friends_list_title": "<b>Друзья</b>\nВыберите друга, чтобы открыть доступные действия.",
        "friend_details": "<b>{name}</b>\nСтатус: {status}",
        "friend_transaction_count": "Общие транзакции: <b>{count}</b>",
        "friend_total_balance": "<b>Итоговый баланс</b>",
        "friend_no_balance": "Расчёты закрыты.",
        "friend_registered": "зарегистрирован(а)",
        "friend_unregistered": "не зарегистрирован(а)",
        "rename_friend": "Переименовать",
        "transfer_friend": "Перенести историю",
        "transfer_friend_to": "Перенести историю к {name}",
        "rename_friend_prompt": "Введите новое личное имя для этого друга.",
        "friend_renamed": "Новое имя друга: {name}.",
        "registered_friends": "Зарегистрированные друзья",
        "guests": "Гости",
        "add_friend": "Добавить друга",
        "no_registered_friends": "У вас пока нет зарегистрированных друзей.",
        "registered_friends_intro": "Ваши зарегистрированные друзья:",
        "choose_friend": "Выберите друга:",
        "no_friends": "Ваш список друзей пуст.",
        "add_friend_prompt": "Выберите пользователя Telegram или добавьте друга по имени.",
        "choose_friend_telegram": "Выбрать пользователя Telegram",
        "add_named_guest": "Добавить друга по имени",
        "friend_name": "Введите отображаемое имя друга.",
        "friend_added": "{name} добавлен(а) в ваш список друзей.",
        "remove_friend": "Удалить {name}",
        "remove_friend_short": "Удалить",
        "remove_friend_question": "Удалить <b>{name}</b> из друзей?",
        "remove_friend_warning": (
            "Существующие расходы и балансы сохранятся. Новый расход с этим человеком "
            "снова добавит его в друзья."
        ),
        "confirm_remove_friend": "Удалить из друзей",
        "keep_friend": "Оставить в друзьях",
        "friend_removed": "{name} удалён(а) из друзей.",
        "friend_already_removed": "Этого человека уже нет в списке друзей.",
        "back_friends": "Назад к друзьям",
    },
}


def translate(locale: Language | str, key: str, **values: object) -> str:
    """Format a localized message, falling back to the English catalog."""
    try:
        selected = Language(locale)
    except ValueError:
        selected = DEFAULT_LANGUAGE
    template = _TEXTS.get(selected, _TEXTS[DEFAULT_LANGUAGE]).get(
        key, _TEXTS[DEFAULT_LANGUAGE][key]
    )
    return template.format(**values)


def button_values(key: str) -> set[str]:
    """Return every localized button label accepted by a text handler."""
    return {catalog[key] for catalog in _TEXTS.values()}


def language_name(language: Language, display_language: Language) -> str:
    """Return a language's localized display name."""
    key = "english" if language is Language.ENGLISH else "russian"
    return translate(display_language, key)


def catalogs() -> Mapping[Language, Mapping[str, str]]:
    """Expose translation catalogs for consistency tests and diagnostics."""
    return _TEXTS
