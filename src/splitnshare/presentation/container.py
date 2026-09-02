"""Define the application-service dependencies injected into Telegram handlers."""

from dataclasses import dataclass

from splitnshare.application.services import (
    ActivityQueryService,
    BalanceQueryService,
    ExpenseQueryService,
    ExpenseService,
    FriendService,
    GuestService,
    SettlementService,
    UserService,
    UserSettingsService,
)


@dataclass(frozen=True, slots=True)
class Services:
    """Bundle use-case services supplied to aiogram handlers."""
    users: UserService
    user_settings: UserSettingsService
    guests: GuestService
    expenses: ExpenseService
    friends: FriendService
    expense_queries: ExpenseQueryService
    balances: BalanceQueryService
    settlements: SettlementService
    activities: ActivityQueryService
