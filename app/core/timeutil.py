"""Bangladesh time (UTC+6, no daylight saving). Avoids needing a timezone database in Docker."""
from datetime import date, datetime, timedelta, timezone

BD_TZ = timezone(timedelta(hours=6))


def now_bd() -> datetime:
    return datetime.now(BD_TZ)


def today_bd() -> date:
    return now_bd().date()


def as_bd(dt: datetime) -> datetime:
    """SQLite returns naive datetimes, PostgreSQL returns aware ones. Make both comparable."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BD_TZ)
    return dt.astimezone(BD_TZ)
