#!/usr/bin/env bash
set -Eeuo pipefail

readonly ENV_FILE="${SPLITNSHARE_ENV_FILE:-/etc/pmd-splitnshare-bot/bot.env}"
readonly PYTHON_BIN="${SPLITNSHARE_PYTHON:-/opt/pmd-splitnshare-bot/.conda/bin/python}"

if [[ ! -r "$ENV_FILE" ]]; then
    echo "Cannot read environment file: $ENV_FILE" >&2
    exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Python executable not found: $PYTHON_BIN" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ -z "${BOT_TOKEN:-}" ]]; then
    echo "BOT_TOKEN is not configured." >&2
    exit 1
fi

"$PYTHON_BIN" - <<'PY'
import asyncio
import os

from aiogram import Bot


async def main() -> None:
    bot = Bot(token=os.environ["BOT_TOKEN"])
    try:
        identity = await bot.get_me()
        print(
            f"Telegram connectivity test: OK "
            f"(@{identity.username}, id={identity.id})"
        )
    finally:
        await bot.session.close()


asyncio.run(main())
PY