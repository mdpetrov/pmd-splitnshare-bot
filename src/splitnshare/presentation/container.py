from dataclasses import dataclass

from splitnshare.application.services import (
    BalanceQueryService,
    ExpenseQueryService,
    ExpenseService,
    GuestService,
    UserService,
)


@dataclass(frozen=True, slots=True)
class Services:
    users: UserService
    guests: GuestService
    expenses: ExpenseService
    expense_queries: ExpenseQueryService
    balances: BalanceQueryService
    default_currency: str

