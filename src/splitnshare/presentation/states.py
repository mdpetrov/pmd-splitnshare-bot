"""Declare finite-state-machine stages for multi-step Telegram flows."""

from aiogram.fsm.state import State, StatesGroup


class AddExpenseStates(StatesGroup):
    """Track progress while a user creates and splits an expense."""
    description = State()
    total = State()
    expense_date = State()
    custom_date = State()
    participants = State()
    manual_name = State()
    exact_amount = State()
    confirm = State()


class TransferGuestStates(StatesGroup):
    """Track guest and target selection during an explicit transfer."""
    target = State()
    confirm = State()


class UserSettingsStates(StatesGroup):
    """Track free-form input while changing user settings."""
    custom_currency = State()


class OnboardingStates(StatesGroup):
    """Track required settings during first-time onboarding."""
    timezone = State()


class SettlementStates(StatesGroup):
    """Track partial-amount entry for a balance settlement."""
    confirm = State()
    amount = State()


class FriendStates(StatesGroup):
    """Track friend creation and private alias editing."""
    choosing = State()
    manual_name = State()
    renaming = State()
