from dataclasses import dataclass

from splitnshare.domain.enums import Language
from splitnshare.domain.timezones import SUPPORTED_TIMEZONES
from splitnshare.presentation.i18n import translate


@dataclass(frozen=True, slots=True)
class TimezoneChoice:
    callback_key: str
    timezone: str
    label_key: str


TIMEZONE_CHOICES = (
    TimezoneChoice("los_angeles", "America/Los_Angeles", "timezone_los_angeles"),
    TimezoneChoice("new_york", "America/New_York", "timezone_new_york"),
    TimezoneChoice("utc", "UTC", "timezone_utc"),
    TimezoneChoice("london", "Europe/London", "timezone_london"),
    TimezoneChoice("madrid", "Europe/Madrid", "timezone_madrid"),
    TimezoneChoice("athens", "Europe/Athens", "timezone_athens"),
    TimezoneChoice("moscow", "Europe/Moscow", "timezone_moscow"),
    TimezoneChoice("dubai", "Asia/Dubai", "timezone_dubai"),
    TimezoneChoice("kolkata", "Asia/Kolkata", "timezone_kolkata"),
    TimezoneChoice("bangkok", "Asia/Bangkok", "timezone_bangkok"),
    TimezoneChoice("singapore", "Asia/Singapore", "timezone_singapore"),
    TimezoneChoice("tokyo", "Asia/Tokyo", "timezone_tokyo"),
    TimezoneChoice("sydney", "Australia/Sydney", "timezone_sydney"),
)

_BY_CALLBACK_KEY = {choice.callback_key: choice for choice in TIMEZONE_CHOICES}
_BY_TIMEZONE = {choice.timezone: choice for choice in TIMEZONE_CHOICES}

assert set(_BY_TIMEZONE) == SUPPORTED_TIMEZONES


def timezone_from_callback_key(callback_key: str) -> str | None:
    choice = _BY_CALLBACK_KEY.get(callback_key)
    return choice.timezone if choice is not None else None


def timezone_label(timezone: str | None, language: Language) -> str:
    if timezone is None:
        return translate(language, "timezone_not_selected")
    choice = _BY_TIMEZONE.get(timezone)
    return translate(language, choice.label_key) if choice is not None else timezone
