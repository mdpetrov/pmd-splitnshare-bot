"""Define scopes in which expenses and balances are calculated."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DirectExpenseContext:
    """Represent expenses that are not associated with a group."""
    group_id: None = None


@dataclass(frozen=True, slots=True)
class GroupExpenseContext:
    """Identify expenses and balances belonging to one group."""
    group_id: UUID


ExpenseContext = DirectExpenseContext | GroupExpenseContext
