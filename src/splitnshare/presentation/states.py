from aiogram.fsm.state import State, StatesGroup


class AddExpenseStates(StatesGroup):
    description = State()
    total = State()
    participants = State()
    manual_name = State()
    exact_amount = State()
    confirm = State()


class TransferGuestStates(StatesGroup):
    target = State()
    confirm = State()

