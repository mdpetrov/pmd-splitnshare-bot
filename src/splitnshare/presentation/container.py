from dataclasses import dataclass

from splitnshare.application.services import (
    BalanceQueryService,
    ExpenseQueryService,
    ExpenseService,
    GuestService,
    UserService,
    UserSettingsService,
)


@dataclass(frozen=True, slots=True)
class Services:
    users: UserService
    user_settings: UserSettingsService
    guests: GuestService
    expenses: ExpenseService
    expense_queries: ExpenseQueryService
    balances: BalanceQueryService
