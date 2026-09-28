"""Assemble the Telegram, application-service, and database components."""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import SimpleEventIsolation
from sqlalchemy.ext.asyncio import AsyncEngine

from splitnshare.application.groups import GroupService
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
from splitnshare.config import Settings
from splitnshare.domain.enums import Language
from splitnshare.infrastructure.database import create_engine, create_session_factory
from splitnshare.infrastructure.fsm_storage import SqlAlchemyFSMStorage
from splitnshare.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from splitnshare.presentation.container import Services
from splitnshare.presentation.middleware import DraftNavigationMiddleware, UserSettingsMiddleware
from splitnshare.presentation.routers import build_router


def build_application(settings: Settings) -> tuple[Bot, Dispatcher, AsyncEngine]:
    """Build the configured bot, dispatcher, services, and database engine."""
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    uow_factory = SqlAlchemyUnitOfWorkFactory(session_factory)
    user_settings = UserSettingsService(
        uow_factory,
        default_currency=settings.default_currency,
        default_language=Language(settings.default_language),
    )
    services = Services(
        users=UserService(uow_factory),
        user_settings=user_settings,
        guests=GuestService(uow_factory),
        expenses=ExpenseService(uow_factory),
        friends=FriendService(uow_factory),
        expense_queries=ExpenseQueryService(uow_factory),
        balances=BalanceQueryService(uow_factory),
        settlements=SettlementService(uow_factory),
        activities=ActivityQueryService(uow_factory),
        groups=GroupService(uow_factory),
    )
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(
        storage=SqlAlchemyFSMStorage(session_factory),
        events_isolation=SimpleEventIsolation(),
        services=services,
    )
    dispatcher.update.outer_middleware(UserSettingsMiddleware(user_settings))
    dispatcher.update.outer_middleware(DraftNavigationMiddleware())
    dispatcher.include_router(build_router())
    return bot, dispatcher, engine
