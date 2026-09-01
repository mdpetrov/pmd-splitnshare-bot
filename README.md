# Splitnshare Bot

Splitnshare is an asynchronous Splitwise-like Telegram bot for recording shared expenses
between registered users and owner-managed guests. The current release focuses on direct
expenses, deterministic splitting, transaction history, and explicit guest transfers.

## Features available now

### Registration and identity

- `/start` creates or updates the caller's registered Telegram identity.
- Registration never searches for, claims, or merges an existing guest profile.
- Registered users and guests have separate participant identities.
- A guest remains active until its owner explicitly transfers it.

### User settings

- Every registered user has a persisted default currency and interface language.
- The default currency is used when a new expense has no explicit currency code.
- Changing the default currency never converts existing expenses or combines balances.
- English and Russian interfaces are available; unsupported Telegram languages fall back
  to English.

### Guests and participant selection

- Expenses can include registered bot users.
- An unregistered Telegram user can be stored as an owner-managed Telegram guest.
- A participant can also be added as a manually named guest without a Telegram ID.
- Re-selecting the same unregistered Telegram user reuses that owner's active guest.
- Guests belonging to different owners remain separate, even when they reference the same
  Telegram user.
- Guest names are never used for automatic matching or merging.
- Participant labels consistently show `Name (@username)` when a Telegram username is
  available. Otherwise, a stable short person code distinguishes repeated names.
- Telegram guest username snapshots are refreshed whenever that guest is selected again.
- Existing friends can be selected while creating another expense.

### Friends

- **Friends** is a private, owner-scoped contact list containing registered users and guests.
- Adding someone does not automatically add the owner to the other user's Friends list.
- Confirming an expense automatically adds its co-participants to the creator's Friends list.
- Friends can also be added directly by selecting a Telegram user or creating a named guest.
- Repeated additions and repeated expenses never create duplicate friendships.
- **Guests** and the explicit guest-transfer flow are nested under **Friends**.
- Guest transfer redirects friendship references to the registered target and safely combines
  duplicates.

### Expense creation

- The **Add expense** flow collects a description, total, optional ISO currency code, and
  participants.
- The creator is included as the payer in the current Telegram flow.
- Each expense supports 2–10 participants, including the payer.
- Participants can be added, reviewed, and removed before confirmation.
- Every multistep stage provides **Back** or **Cancel** navigation where applicable.
- A final review displays the payer and each participant's share before saving.
- Expense, split, and debt records are committed in one database transaction.

### Splitting and money handling

- Equal splitting distributes remainder minor units deterministically by participant order.
- Exact splitting requires an amount for every participant and rejects totals that do not
  reconcile exactly with the expense total.
- Money is stored as integer minor units rather than binary floating-point values.
- Balances and debts remain isolated by ISO currency code; currencies are never combined or
  converted automatically.

### Transactions

- **Transactions** shows the registered user's active expense history.
- History is cursor-paginated and provides a detailed view of each expense and its shares.
- Only the expense creator can delete it.
- Deletion is soft: the historical database record remains, while the expense is excluded
  from active history and balances.

### Balances

- **Balances** separates amounts the current user owes from amounts owed to them.
- Each balance is shown against the corresponding registered user or guest.
- Balances remain separate by currency and are never converted or combined.
- Soft-deleted expenses do not contribute to outstanding balances.

### Explicit guest transfer

- **Friends → Guests** lists active guests owned by the current user.
- A guest can be transferred only by its owner and only to a user who has already registered
  with the bot.
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
  transfer; their approval is not required.
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

The test suite covers money validation, equal and exact splits, registration isolation,
owner-scoped guests, explicit guest transfer, split consolidation, debt regeneration, group
membership consolidation, role preservation, and transfer authorization. Ruff and strict
mypy configuration are included for source-quality and type checks.
