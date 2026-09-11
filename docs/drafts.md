# Persistent drafts

Active aiogram state and entered values are stored in `conversation_states` in the configured
application database. Unfinished expenses additionally have independent snapshots in
`expense_drafts`. PostgreSQL persists both on disk using the existing database volume;
no Redis, additional server, or runtime dependency is introduced.

## Using drafts

- Each new expense receives its own draft ID. Accepted inputs and step changes are saved.
- After a restart, the user can keep answering the last prompt. `/drafts` or the **Drafts**
  menu button recreates the saved step and keyboard if the original message is hard to find.
- Starting another expense, returning to the menu, `/start`, and Cancel preserve unfinished
  expense snapshots. The review screen calls this **Save draft & exit**.
- Select a draft's title to resume its saved step, including partially entered exact shares.
  **Edit** starts at the description while keeping the other stored fields available.
- **Delete** explicitly removes an unfinished expense after confirmation. Merely leaving an
  expense does not discard it. Saving consumes its snapshot. There is no automatic expiry.
- Other active forms (settings, friends, settlements, transfers) also survive a process restart.
  They remain single active flows; the multiple-draft library is for unfinished expenses.
  Editing an already saved expense is still outside this feature.

The registry key includes bot, chat, Telegram user, topic, business connection, and destiny.
Draft listing, activation, and deletion check that complete key. Snapshots are private to
that conversation. Account deletion purges associated snapshots and active sessions.
Backups should cover these tables alongside the ledger.

## Saving and recovery

Conversation writes and their expense checkpoints commit together. A process failure between
two handler operations can leave the earlier step visible, but committed entered values are
retained. Partially entered exact shares are restored, including recovery when all shares
were written immediately before a restart.

Final confirmation identifies the active draft. Expense creation locks and consumes that
draft, clears its active session, and saves the expense, shares, debts, and friendships in
one transaction. A failure rolls everything back; a retry after commit cannot create the same
draft again, even if the success message was never delivered. Participant notifications
retain their existing best-effort delivery behavior.

Final validation still checks current participant availability and split totals. If a person
has become unavailable while an expense was paused, edit the draft's participants before
saving. Telegram messages that have not reached the bot, and invalid input rejected by a
handler, cannot be recovered from these snapshots.

## Deploying

Stop the bot, run `python -m alembic upgrade head` to apply revision `20260911_0011`, then start
the updated bot. Existing drafts held only in the old process's RAM cannot be recovered by
this migration. Future drafts persist automatically. Keep the PostgreSQL volume when replacing
containers; deleting the database volume removes drafts as well as other application data.

Use one polling process. Database-backed state does not make update handlers safe to run in
multiple independent workers; this version uses in-process per-conversation event locks.
Downgrading this revision drops saved conversation state and drafts, while preserving ledger
tables. Future changes to draft formats or currency precision must explicitly handle stored
snapshots rather than silently reinterpreting their values.
