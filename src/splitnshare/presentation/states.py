from aiogram.fsm.state import State, StatesGroup


class AddExpenseStates(StatesGroup):
    description = State()
    total = State()
    expense_date = State()
    custom_date = State()
    participants = State()
    manual_name = State()
    exact_amount = State()
    confirm = State()


class TransferGuestStates(StatesGroup):
    target = State()
    confirm = State()


class UserSettingsStates(StatesGroup):
    custom_currency = State()


class OnboardingStates(StatesGroup):
    timezone = State()


class SettlementStates(StatesGroup):
    confirm = State()
    amount = State()


class FriendStates(StatesGroup):
    choosing = State()
    manual_name = State()
    renaming = State()
