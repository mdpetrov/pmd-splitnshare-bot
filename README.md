# Splitnshare Bot

Splitnshare is an asynchronous Splitwise-like Telegram bot for recording shared expenses
between registered and unregistered friends. The current release focuses on direct expenses,
deterministic splitting, transaction history, and balances.

## Features available now

### Registration and identity

- `/start` creates or updates the caller's registered Telegram identity.
- After setup, `/start` shows a visible main menu for expenses, activity, balances,
  friends, and settings. It can also be used to reopen the menu later.
- The returning-user welcome summarizes total amounts owed and receivable separately for
  each currency without netting unrelated counterparties together.
- The persistent reply keyboard keeps the same actions available as quick shortcuts.
- Registration automatically finds every active temporary profile carrying the same shared
  Telegram user ID and transfers its complete history to the registered identity.
- Registration and matching transfers commit atomically: if any transfer fails, neither the
  registration nor a partial transfer is committed.

### User settings

- Every registered user has a persisted default currency, interface language, and timezone.
- New users choose their timezone before the main menu opens and are told that currency and
  language can be changed later in **Settings**.
- Timezone choices use readable `UTC±offset (cities)` labels while the database stores an IANA
  city-based timezone, allowing daylight-saving changes to be applied correctly.
- Existing users receive `UTC` during migration and may change it from **Settings**.
- The default currency is used when a new expense has no explicit currency code.
- Changing the default currency never converts existing expenses or combines balances.
- English and Russian interfaces are available; unsupported Telegram languages fall back
  to English.

### Participant selection

- Expenses can include registered bot users.
- An unregistered Telegram user can be stored as an owner-managed friend.
- A friend can also be added manually by name without a Telegram ID.
- Re-selecting the same unregistered Telegram user reuses that owner's internal participant.
- If that Telegram user later registers, every matching owner-managed temporary profile is
  transferred automatically. Future selections resolve to the registered identity and cannot
  create a second active friend entry.
- Unregistered friends belonging to different owners remain separate, even when they
  reference the same Telegram user.
- Names are never used for automatic matching or merging; manually named friends are never
  transferred automatically.
- Participant labels consistently show `Name (@username)` when a Telegram username is
  available. Otherwise, a stable short person code distinguishes repeated names.
- Telegram username snapshots are refreshed whenever an unregistered friend is selected again.
- Existing friends can be selected while creating another expense.

### Friends

- **Friends** is one private, owner-scoped list containing both registered and unregistered
  friends; the Telegram UI does not expose separate identity categories.
- Every friend appears as a button opening an extensible detail screen.
- The detail screen shows the number of active shared transactions and a currency-separated
  balance summary, making the impact of a possible history transfer easier to understand.
- The detail screen supports a private rename, friend removal, and an owner-only
  **Transfer history** fallback for unregistered friends, including manually named profiles.
- When the hinted Telegram account has registered, the transfer action identifies that
  account and opens the review directly; otherwise it asks the owner to select a registered
  target.
- Renaming creates an owner-specific alias and never modifies the person's registered name
  or another user's view of them.
- Adding someone does not automatically add the owner to the other user's Friends list.
- Confirming an expense automatically adds its co-participants to the creator's Friends list.
- Friends can also be added directly by selecting a Telegram user or entering a name.
- Repeated additions and repeated expenses never create duplicate friendships.
- Any friend can be removed after an explicit confirmation.
- Removing a friend archives only the private friendship: expenses, balances, identities,
  and internal participant profiles remain unchanged.
- A later expense with a removed person automatically restores the friendship.

### Expense creation

- The **Add expense** flow collects a description, total, optional ISO currency code, and
  participants.
- The flow records when the expense happened using **Now**, relative-time presets, or a
  custom local date and time interpreted in the creator's configured timezone.
- Expense occurrence times are stored in UTC and displayed in each viewer's local timezone;
  the separate creation timestamp remains available for auditing.
- The creator is included as the payer in the current Telegram flow.
- Each expense supports 2–10 participants, including the payer.
- Participants can be added, reviewed, and removed before confirmation.
- Every multistep stage provides **Back** or **Cancel** navigation where applicable.
- A final review displays the payer and each participant's share before saving.
- Expense, split, and debt records are committed in one database transaction.
- After that commit, every registered participant except the creator receives a localized,
  best-effort Telegram notification showing the expense and what they owe or are owed.
- Unregistered friends cannot receive notifications, and delivery failures never roll back
  a saved expense.

### Splitting and money handling

- Equal splitting distributes remainder minor units deterministically by participant order.
- Exact splitting requires an amount for every participant and rejects totals that do not
  reconcile exactly with the expense total.
- Money is stored as integer minor units rather than binary floating-point values.
- Balances and debts remain isolated by ISO currency code; currencies are never combined or
  converted automatically.

### Activity

- **Activity** shows the registered user's active expense history.
- Settlement payments appear in the same chronological feed and show who paid whom,
  who recorded the payment, and the currency-specific amount.
- History is cursor-paginated and provides a detailed view of each expense and its shares.
- Only the expense creator can delete it.
- Deletion is soft: the historical database record remains, while the expense is excluded
  from active history and balances.

### Balances

- **Balances** separates amounts the current user owes from amounts owed to them.
- Each balance is shown against the corresponding registered or unregistered friend.
- Selecting a person opens their per-currency balance breakdown, settlement actions, and
  cursor-paginated history of expenses and settlement payments shared with that person.
- Balances remain separate by currency and are never converted or combined.
- Soft-deleted expenses do not contribute to outstanding balances.

### Settling balances

- Every outstanding person-and-currency balance provides a **Settle** action.
- A user can record the complete outstanding payment or enter a smaller partial amount.
- The payment direction is derived from the balance: the current user can record money they
  paid or money they received without manually choosing payer and recipient.
- Settlements are stored as separate auditable payment records and immediately reduce both
  participants' balances.
- A settlement cannot exceed the current outstanding amount and never combines currencies.
- Registered and owner-managed unregistered friends can both participate in settlements.
- Explicit guest transfer also moves settlement history to the selected registered identity.

### Internal unregistered-participant transfer

- The domain retains an internal guest-profile concept for unregistered identities, but it is
  not presented as a separate section in the Telegram UI.
- Transfer logic can replace a temporary identity across all history and memberships; it does
  not send money or merge groups.
- When a hinted Telegram account registers, the backend automatically transfers every matching
  active profile, including separate profiles owned by different users. Manually named profiles
  have no Telegram identity hint and remain available for an explicit transfer.
- Manual transfer can be initiated only by the profile owner and can target only a user who has
  registered with the bot. Registration-triggered transfer is authorized by the matching
  authenticated Telegram ID.
- The confirmation preview shows affected expenses, groups, and recorded debt amounts by
  currency.
- Transfer moves all payer references, expense splits, debts, and group memberships in one
  atomic database transaction.
- When the guest and target already share an expense, their shares are consolidated without
  changing the expense total.
- When both already belong to a group, the target's existing membership and role are
  preserved.
- A completed guest becomes inactive and cannot be selected for new expenses.
- The target receives a best-effort informational Telegram message after a successful
  transfer naming its initiator and showing active transferred expense totals separately by
  currency; their approval is not required.
- Transfers cannot be reversed through the current Telegram interface.

## Architecture already prepared for expansion

- Direct and group expense contexts are represented separately in the domain.
- Group and group-membership tables are included in the database schema.
- Application services are separated from aiogram routers and SQLAlchemy repositories.
- Expense creation and guest transfer use explicit transaction boundaries.
- The presentation layer uses aiogram routers, keyboards, callbacks, and FSM states, allowing
  new buttons and user flows to be added without moving business rules into handlers.

## Not available in the Telegram UI yet

- Creating and managing groups.
- Group-scoped expense entry, history, and balances.
- Settlement payments.
- Editing an existing expense.
- Selecting a payer other than the creator.
- Exchange-rate conversion.
- Recurring expenses.
- AI-assisted expense parsing.

The current FSM storage is in memory and is intended for a single bot process. Durable FSM
storage such as Redis will be needed before running multiple bot instances.

## Automated coverage

The test suite covers money validation, equal and exact splits, automatic registration transfer,
owner-scoped guests, manual guest transfer, split consolidation, debt regeneration, group
membership consolidation, role preservation, and transfer authorization. Ruff and strict
mypy configuration are included for source-quality and type checks.

All package and Alembic modules, classes, functions, and methods must include a concise
docstring that explains their responsibility. Ruff checks public documentation, and the test
suite also enforces descriptions for private helpers, constructors, and migration functions so
future features and schema changes remain readable.
