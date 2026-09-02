from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from splitnshare.domain.enums import Language
from splitnshare.domain.errors import ValidationError


def parse_local_datetime(
    value: str,
    timezone: str,
    *,
    now: datetime | None = None,
) -> datetime:
    text = " ".join(value.strip().split())
    local_now = (now or datetime.now(UTC)).astimezone(ZoneInfo(timezone))
    parsed: datetime | None = None
    for pattern in ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(text, pattern)
            break
        except ValueError:
            pass
    if parsed is None:
        try:
            parsed = datetime.strptime(
                f"{local_now.year}.{text}", "%Y.%d.%m %H:%M"
            )
        except ValueError as exc:
            raise ValidationError("Invalid local date and time.") from exc

    zone = ZoneInfo(timezone)
    local = parsed.replace(tzinfo=zone)
    utc_value = local.astimezone(UTC)
    # ZoneInfo normalizes nonexistent wall-clock times during a DST jump. Reject
    # those values instead of silently storing a different time.
    round_trip = utc_value.astimezone(zone).replace(tzinfo=None)
    if round_trip != parsed:
        raise ValidationError("That local time does not exist in this timezone.")
    return utc_value


def format_local_datetime(
    value: datetime,
    timezone: str,
    language: Language,
) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    local = value.astimezone(ZoneInfo(timezone))
    pattern = "%d.%m.%Y %H:%M" if language is Language.RUSSIAN else "%Y-%m-%d %H:%M"
    return f"{local.strftime(pattern)} {local.tzname() or timezone}"
