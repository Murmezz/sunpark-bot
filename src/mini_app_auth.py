"""Exchange fresh Telegram initData for a bounded, launch-bound app session."""
import hashlib
import hmac
import json
import re
import time
from urllib.parse import parse_qsl

from menu_preview import validate_init_data

SESSION_TTL = 12 * 60 * 60


def session_signature(raw, token, issued):
    key = hmac.new(str(token).encode(), b"SunparkMiniAppSessionV1", hashlib.sha256).digest()
    return hmac.new(key, f"{issued}\n{raw}".encode(), hashlib.sha256).hexdigest()


def authenticate_app(raw, token, session=None, now=None):
    """A session can only be issued after the original one-hour Telegram check.

    Its MAC binds the exact signed launch data and issuance time. Reusing it
    never extends the twelve-hour lifetime; roles are checked by the API on
    every request, and token rotation invalidates existing sessions.
    """
    current = int(time.time() if now is None else now)
    if not isinstance(raw, str) or not raw or len(raw) > 16384:
        raise ValueError("Missing Telegram launch data")
    if isinstance(session, str) and re.fullmatch(r"v1\.[0-9]{1,12}\.[0-9a-f]{64}", session):
        _, stamp, supplied = session.split(".")
        issued = int(stamp)
        if -30 <= current - issued <= SESSION_TTL and hmac.compare_digest(session_signature(raw, token, issued), supplied):
            user = json.loads(dict(parse_qsl(raw, keep_blank_values=True, strict_parsing=True))["user"])
            uid = user.get("id")
            if type(uid) is int and uid > 0:
                return uid, session
    uid = validate_init_data(raw, token, now=current)
    return uid, f"v1.{current}.{session_signature(raw, token, current)}"
