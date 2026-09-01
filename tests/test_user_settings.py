import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from splitnshare.application.dto import (
    TelegramIdentity,
    UpdateUserSettingsCommand,
)
from splitnshare.application.services import UserService, UserSettingsService
from splitnshare.domain.enums import Language
from splitnshare.domain.errors import ValidationError
from splitnshare.infrastructure.database import create_session_factory
from splitnshare.infrastructure.models import Base
from splitnshare.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from splitnshare.presentation.i18n import catalogs, translate
from splitnshare.presentation.keyboards import main_menu


@pytest.fixture
async def settings_services():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = SqlAlchemyUnitOfWorkFactory(create_session_factory(engine))
    yield (
        UserService(factory),
        UserSettingsService(factory, default_currency="EUR"),
    )
    await engine.dispose()


async def test_settings_are_created_from_application_and_telegram_defaults(
    settings_services,
) -> None:
    users, settings = settings_services
    person = await users.register_or_update(
        TelegramIdentity(
            telegram_user_id=501,
            first_name="User",
            language_code="ru-RU",
        )
    )

    created = await settings.get_or_create(
        person.id, preferred_language="ru-RU"
    )
    repeated = await settings.get_or_create(
        person.id, preferred_language="en"
    )

    assert created.default_currency == "EUR"
    assert created.language is Language.RUSSIAN
    assert repeated == created


async def test_settings_can_be_updated_and_found_by_telegram_id(settings_services) -> None:
    users, settings = settings_services
    person = await users.register_or_update(
        TelegramIdentity(telegram_user_id=502, first_name="User")
    )
    await settings.get_or_create(person.id)

    updated = await settings.update(
        UpdateUserSettingsCommand(
            person_id=person.id,
            default_currency="usd",
            language=Language.RUSSIAN,
        )
    )
    loaded = await settings.find_by_telegram_id(502)

    assert updated.default_currency == "USD"
    assert updated.language is Language.RUSSIAN
    assert loaded == updated


async def test_settings_reject_invalid_currency(settings_services) -> None:
    users, settings = settings_services
    person = await users.register_or_update(
        TelegramIdentity(telegram_user_id=503, first_name="User")
    )
    await settings.get_or_create(person.id)

    with pytest.raises(ValidationError):
        await settings.update(
            UpdateUserSettingsCommand(person_id=person.id, default_currency="EURO")
        )


def test_locales_have_the_same_messages_and_localized_menu() -> None:
    available = catalogs()
    assert set(available[Language.ENGLISH]) == set(available[Language.RUSSIAN])
    assert translate(Language.RUSSIAN, "settings") == "⚙️ Настройки"

    keyboard = main_menu(Language.RUSSIAN)
    assert keyboard.keyboard[0][0].text == "➕ Добавить расход"
    assert keyboard.keyboard[1][0].text == "💰 Балансы"
    assert keyboard.keyboard[2][0].text == "⚙️ Настройки"
