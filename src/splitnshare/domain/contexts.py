from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DirectExpenseContext:
    group_id: None = None


@dataclass(frozen=True, slots=True)
class GroupExpenseContext:
    group_id: UUID


ExpenseContext = DirectExpenseContext | GroupExpenseContext

