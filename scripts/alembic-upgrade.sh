#!/bin/bash
set -a
source /etc/pmd-splitnshare-bot/bot.env
set +a
cd /opt/pmd-splitnshare-bot/app
/opt/pmd-splitnshare-bot/.conda/bin/python -m alembic upgrade head
/opt/pmd-splitnshare-bot/.conda/bin/python -m alembic current
/opt/pmd-splitnshare-bot/.conda/bin/python -m splitnshare.infrastructure.database_health
