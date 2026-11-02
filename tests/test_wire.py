import json
import math
from pathlib import Path
import struct

import pytest

from multibox.simulation import Config, World
from multibox.wire import Decoder, Encoder, WireError, pack_paint, unpack_paint

GOLD = json.loads((Path(__file__).parent / "fixtures/wire-v2.json").read_text())


def golden_frame():
    return bytes.fromhex(
        GOLD["header_hex"] + GOLD["player_hex"] + GOLD["paint_byte_hex"] * GOLD["paint_bytes"]
    )


def test_cross_language_golden_encode_and_decode():
    world = World()
    world.next_id = 2**64 - 1
    p = world.add_player("同学", now=0)
    p.body.position = 100.0625, 200.125
    p.body.angle = math.pi / 2
    p.body.velocity = 0, -123.5
    p.team, p.jump_ready, p.seq = 2, True, 2**31 - 1
    world.tick, world.round, world.remaining = 60, 3, 123.456
    world.paint[:] = (GOLD["paint_pattern"] * GOLD["paint_repeats"]).encode()
    encoder = Encoder()
    encoder.revision = int(GOLD["metadata"]["revision"]) - 1
    packet = encoder.packet(world)
    assert json.loads(packet.metadata) == GOLD["metadata"]
    assert packet.frame == golden_frame()
    decoder = Decoder()
    decoder.metadata(GOLD["metadata"])
    state = decoder.frame(packet.frame)
    e = GOLD["expected"]
    assert state["players"] == [
        [e["id"], e["nickname"], e["team"], e["x"], e["y"], e["angle"], e["vy"], e["jump"], e["seq"]]
    ]
    assert state["coverage"] == e["coverage"]
    assert state["remaining"] == e["remaining"]
    assert state["paint"] == GOLD["paint_pattern"] * GOLD["paint_repeats"]
    assert len(packet.frame) == 40 + 14 + 375


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5, 1500, 6000])
def test_paint_all_sizes_padding_and_maximum(size):
    paint = ("0120" * 1500)[:size]
    packed = pack_paint(paint)
    assert len(packed) == (size + 3) // 4
    assert unpack_paint(packed, size) == paint
    if size % 4:
        bad = bytearray(packed)
        bad[-1] |= 1 << (2 * (size % 4))
        with pytest.raises(WireError):
            unpack_paint(bad, size)


@pytest.mark.parametrize("paint", ["", "3", "0" * 6001])
def test_invalid_paint_rejected(paint):
    with pytest.raises(WireError):
        pack_paint(paint)


def test_maximum_grid_and_roster_round_trip():
    world = World(Config(cell_size=12, max_players=200))
    for i in range(200):
        world.add_player(f"box {i}", now=0)
    packet = Encoder().packet(world)
    assert len(packet.frame) == 4340
    decoder = Decoder()
    decoder.metadata(json.loads(packet.metadata))
    state = decoder.frame(packet.frame)
    assert len(state["players"]) == 200 and len(state["paint"]) == 6000


def test_slot_reuse_requires_new_metadata_and_never_aliases_stale_frames():
    world = World()
    a = world.add_player("a", now=0)
    encoder = Encoder()
    old = encoder.packet(world)
    decoder = Decoder()
    decoder.metadata(json.loads(old.metadata))
    decoder.frame(old.frame)
    world.remove_player(a.id)
    b = world.add_player("b", now=1)
    world.step(1)
    new = encoder.packet(world)
    assert new.revision == old.revision + 1
    assert json.loads(new.metadata)["players"][0][0] == 1
    with pytest.raises(WireError, match="metadata"):
        Decoder().frame(new.frame)
    decoder.metadata(json.loads(new.metadata))
    assert decoder.frame(old.frame) is None
    state = decoder.frame(new.frame)
    assert [p[0] for p in state["players"]] == [b.id]
    assert decoder.frame(new.frame) is None  # duplicate tick
    conflict = json.loads(new.metadata)
    conflict["players"][0][1] = "wrong"
    with pytest.raises(WireError):
        decoder.metadata(conflict)


@pytest.mark.parametrize(
    "offset,data",
    [
        (0, b"BAD!"),
        (8, bytes(8)),
        (4, b"\x03"),
        (5, b"\xff"),
        (6, b"\xc9\x00"),
        (36, b"\x00\x00"),
        (38, b"\x01\x00"),
        (40, b"\x00\x00"),
        (49, b"\x80"),
        (50, b"\x00\x00\x00\x80"),
        (54, b"\x03"),
    ],
)
def test_malformed_fields_rejected(offset, data):
    frame = bytearray(golden_frame())
    frame[offset : offset + len(data)] = data
    decoder = Decoder()
    decoder.metadata(GOLD["metadata"])
    with pytest.raises(WireError):
        decoder.frame(frame)


@pytest.mark.parametrize("delta", [-1, 1, -400])
def test_frame_length_is_exact(delta):
    frame = golden_frame()
    frame = frame[:delta] if delta < 0 else frame + b"\x00"
    decoder = Decoder()
    decoder.metadata(GOLD["metadata"])
    with pytest.raises(WireError):
        decoder.frame(frame)


def test_no_silent_numeric_overflow_and_no_string_id_truncation():
    world = World()
    p = world.add_player("box", now=0)
    for field, value in [("tick", 2**53), ("round", 2**32), ("remaining", 2**32 / 1000)]:
        old = getattr(world, field)
        setattr(world, field, value)
        with pytest.raises(WireError):
            Encoder().packet(world)
        setattr(world, field, old)
    for xy in [(-129, 20), (5000, 20), (float("nan"), 20)]:
        p.body.position = xy
        with pytest.raises(WireError):
            Encoder().packet(world)
    p.body.position = (100, 100)
    p.seq = 2**31
    with pytest.raises(WireError):
        Encoder().packet(world)
    world.next_id = 2**64
    count = len(world.space.bodies)
    with pytest.raises(ValueError, match="identity"):
        world.add_player("overflow", now=0)
    assert len(world.space.bodies) == count


def test_metadata_rejects_invalid_versions_duplicate_slots_ids_and_unbounded_revisions():
    for change in [
        {"v": 1},
        {"revision": "18446744073709551616"},
        {"revision": "01"},
        {"players": [[1, "a", "a"], [1, "b", "b"]]},
        {"players": [[1, "a", "a"], [2, "a", "b"]]},
        {"players": [[201, "a", "a"]]},
        {"world": [1200, 720, 24, 1]},
    ]:
        with pytest.raises(WireError):
            Decoder().metadata(GOLD["metadata"] | change)


def test_revision_overflow_and_decoder_subview_are_explicit():
    world = World()
    world.add_player("a", now=0)
    encoder = Encoder()
    encoder.revision = 2**64 - 1
    with pytest.raises(WireError, match="revision"):
        encoder.packet(world)
    decoder = Decoder()
    decoder.metadata(GOLD["metadata"])
    assert decoder.frame(memoryview(b"prefix" + golden_frame())[6:])["tick"] == 60
