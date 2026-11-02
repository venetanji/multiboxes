"""Small strict JSON protocol. Clients request input; they cannot write game state."""

import json

from .simulation import Input

MAX_MESSAGE_BYTES = 512
INPUT_KEYS = {"type", "seq", "left", "right", "jump", "down"}


class ProtocolError(ValueError):
    pass


def decode(raw: str) -> dict:
    if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message too large")
    try:
        message = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ProtocolError("invalid JSON") from error
    if not isinstance(message, dict):
        raise ProtocolError("message must be an object")
    return message


def parse_join(message: dict) -> str:
    if set(message) != {"type", "v", "nickname"} or message["type"] != "join":
        raise ProtocolError("expected one join message")
    if type(message["v"]) is not int or message["v"] != 2:
        raise ProtocolError("unsupported protocol version")
    name = message["nickname"]
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 24 or not name.isprintable():
        raise ProtocolError("nickname must be 1..24 printable characters")
    return name.strip()


def parse_input(message: dict) -> tuple[int, Input]:
    if set(message) != INPUT_KEYS or message["type"] != "input":
        raise ProtocolError("expected input only")
    seq = message["seq"]
    if type(seq) is not int or not 0 <= seq < 2**31:
        raise ProtocolError("seq must be a nonnegative 31-bit integer")
    for key in ("left", "right", "jump", "down"):
        if type(message[key]) is not bool:
            raise ProtocolError("buttons must be booleans")
    return seq, Input(**{key: message[key] for key in ("left", "right", "jump", "down")})


class RateLimiter:
    """Per-session 60 messages/s token bucket, with a 90-message burst ceiling."""

    def __init__(self, *, now: float):
        self.at, self.tokens = now, 90.0

    def allow(self, now: float) -> bool:
        self.tokens = min(90, self.tokens + max(0, now - self.at) * 60)
        self.at = now
        if self.tokens < 1 - 1e-9:
            return False
        self.tokens -= 1
        return True
