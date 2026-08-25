from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncEngine

from splitnshare.application.services import (
    BalanceQueryService,
    ExpenseQueryService,
    ExpenseService,
    GuestService,
    UserService,
)
from splitnshare.config import Settings
from splitnshare.infrastructure.database import create_engine, create_session_factory
from splitnshare.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from splitnshare.presentation.container import Services
from splitnshare.presentation.routers import build_router


def build_application(settings: Settings) -> tuple[Bot, Dispatcher, AsyncEngine]:
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    uow_factory = SqlAlchemyUnitOfWorkFactory(session_factory)
    services = Services(
        users=UserService(uow_factory),
        guests=GuestService(uow_factory),
        expenses=ExpenseService(uow_factory),
        expense_queries=ExpenseQueryService(uow_factory),
        balances=BalanceQueryService(uow_factory),
        default_currency=settings.default_currency,
    )
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage(), services=services)
    dispatcher.include_router(build_router())
    return bot, dispatcher, engine

