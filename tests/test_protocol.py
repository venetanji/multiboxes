import json

import pytest

from multibox.protocol import ProtocolError, RateLimiter, decode, parse_input, parse_join
from multibox.simulation import Input


def test_valid_messages_and_no_client_authority():
    assert parse_join(decode('{"type":"join","v":2,"nickname":"  Box  "}')) == "Box"
    seq, buttons = parse_input(
        {"type": "input", "seq": 1, "left": False, "right": True, "jump": False, "down": True}
    )
    assert seq == 1 and buttons == Input(right=True, down=True)


@pytest.mark.parametrize(
    "raw", ["[]", "null", "NaN", "{", "x" * 513, json.dumps({"x": "界" * 180}, ensure_ascii=False)]
)
def test_decode_rejects_invalid_or_oversized(raw):
    with pytest.raises(ProtocolError):
        decode(raw)


@pytest.mark.parametrize(
    "changes",
    [
        {"v": 3},
        {"v": 1},
        {"v": True},
        {"nickname": ""},
        {"nickname": "x" * 25},
        {"nickname": "bad\nname"},
        {"team": 1},
        {"id": "other"},
    ],
)
def test_join_rejects_invalid_or_spoofed(changes):
    with pytest.raises(ProtocolError):
        parse_join({"type": "join", "v": 2, "nickname": "Box"} | changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"seq": -1},
        {"seq": True},
        {"seq": 1.2},
        {"seq": 2**31},
        {"left": 1},
        {"down": "true"},
        {"x": 500},
        {"type": "reset"},
    ],
)
def test_input_is_strict_and_bounded(changes):
    with pytest.raises(ProtocolError):
        parse_input(
            {"type": "input", "seq": 1, "left": False, "right": False, "jump": False, "down": False} | changes
        )


def test_rate_limiter_has_bounded_burst_and_refills():
    limiter = RateLimiter(now=0)
    assert all(limiter.allow(0) for _ in range(90))
    assert not limiter.allow(0)
    assert limiter.allow(1 / 60)
    assert not limiter.allow(1 / 60)
    assert limiter.allow(100)
    assert limiter.tokens <= 90
