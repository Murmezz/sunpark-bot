import re
from datetime import date, datetime


def valid_date(value, today=None):
    value = str(value or "").strip()
    parsed = None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt).date()
            break
        except (ValueError, AttributeError):
            pass
    return bool(parsed and parsed >= (today or date.today()))


def valid_time(value):
    return bool(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", str(value or "").strip()))


def valid_guests(value):
    try:
        count = int(str(value).strip())
        return 1 <= count <= 200
    except (TypeError, ValueError):
        return False


def normalize_phone(value):
    raw = str(value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    if not 10 <= len(digits) <= 15:
        return None
    return "+" + digits
