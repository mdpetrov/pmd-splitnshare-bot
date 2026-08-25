# Splitnshare Bot

An asynchronous Splitwise-like Telegram bot supporting registered users, owner-managed
guests, equal or exact expense splits, debt tracking, transaction history, soft deletion,
and explicit all-or-nothing guest transfers. Registration never claims or merges guests.

## Run locally

1. Install Python 3.12 or newer and create a virtual environment.
2. Install the project: `pip install -e ".[dev]"`.
3. Copy `.env.example` to `.env` and set `BOT_TOKEN`.
4. Start PostgreSQL: `docker compose up -d postgres`.
5. Apply the schema: `alembic upgrade head`.
6. Start long polling: `python -m splitnshare`.

The default PostgreSQL URL is
`postgresql+asyncpg://splitnshare:splitnshare@localhost:5432/splitnshare`.

## User flows

- `/start` creates or updates only the registered Telegram identity.
- **Add expense** collects a description, total/currency, registered or guest participants,
  split method, review, and confirmation.
- **Transactions** shows paginated active history and creator-only deletion.
- **People** lists guests owned by the current user and provides an explicit transfer flow.

A guest transfer is irreversible through the bot. It moves every split, payer reference,
debt, and group membership in one database transaction. If the target already occurs in an
expense, their shares are consolidated. If they already belong to a group, their existing
role is preserved.

## Development

Run checks with:

```text
ruff check .
mypy src
pytest
```

Group tables and group-aware service parameters are present, but group-facing Telegram UI
is intentionally deferred. The local FSM uses in-memory storage; replace it with Redis for
multi-instance deployment.

