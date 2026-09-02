"""Run the Splitnshare Telegram bot polling process."""

import asyncio
import logging

from splitnshare.config import get_settings
from splitnshare.presentation.app import build_application


async def run() -> None:
    """Build the application and poll Telegram until shutdown."""
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    bot, dispatcher, engine = build_application(settings)
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    """Start the asynchronous bot from the console entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
