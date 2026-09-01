from aiogram import Router
from aiogram.types import ErrorEvent

from splitnshare.domain.errors import DomainError
from splitnshare.presentation.routers.expenses import router as expenses_router
from splitnshare.presentation.routers.people import router as friends_router
from splitnshare.presentation.routers.settings import router as settings_router
from splitnshare.presentation.routers.start import router as start_router


def build_router() -> Router:
    router = Router(name="root")
    router.include_routers(start_router, settings_router, expenses_router, friends_router)

    @router.error()
    async def handle_error(event: ErrorEvent) -> bool:
        update = event.update
        message = update.message or (
            update.callback_query.message if update.callback_query is not None else None
        )
        if isinstance(event.exception, DomainError) and message is not None:
            await message.answer(str(event.exception))
            return True
        return False

    return router
