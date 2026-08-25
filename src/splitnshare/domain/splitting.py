from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from splitnshare.domain.enums import SplitMethod
from splitnshare.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class Allocation:
    person_id: UUID
    owed_minor: int
    position: int


class EqualSplitStrategy:
    method = SplitMethod.EQUAL

    def allocate(self, total_minor: int, participants: Sequence[UUID]) -> list[Allocation]:
        _validate_participants(participants)
        quotient, remainder = divmod(total_minor, len(participants))
        if quotient == 0:
            raise ValidationError("The total is too small for this number of participants.")
        return [
            Allocation(person_id, quotient + (position < remainder), position)
            for position, person_id in enumerate(participants)
        ]


class ExactSplitStrategy:
    method = SplitMethod.EXACT

    def allocate(
        self,
        total_minor: int,
        participants: Sequence[UUID],
        exact_amounts: Mapping[UUID, int],
        payer_id: UUID,
    ) -> list[Allocation]:
        _validate_participants(participants)
        if set(exact_amounts) != set(participants):
            raise ValidationError("An exact amount is required for every participant.")
        if sum(exact_amounts.values()) != total_minor:
            raise ValidationError("Exact amounts must add up to the expense total.")
        if exact_amounts[payer_id] < 0:
            raise ValidationError("The payer share cannot be negative.")
        if any(amount <= 0 for person_id, amount in exact_amounts.items() if person_id != payer_id):
            raise ValidationError("Every non-payer must owe more than zero.")
        return [
            Allocation(person_id, exact_amounts[person_id], position)
            for position, person_id in enumerate(participants)
        ]


def _validate_participants(participants: Sequence[UUID]) -> None:
    if not 2 <= len(participants) <= 10:
        raise ValidationError("An expense must have between 2 and 10 participants.")
    if len(set(participants)) != len(participants):
        raise ValidationError("A participant cannot be added twice.")

