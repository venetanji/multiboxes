"""Protocol v2: complete gameplay frames plus reliable, versioned JSON metadata.

Little endian throughout. No gameplay delta or implicit truncation. Wire slots
are connection-roster IDs (1..200), never truncated lifetime identity strings.
See docs/protocol.md for byte offsets and the shared Python/JS golden vector.
"""

from dataclasses import dataclass
import json
import math
import struct

VERSION = 2
MAX_PLAYERS = 200
MAX_CELLS = 6000
MAX_U64 = 2**64 - 1
MAX_TICK = 2**53 - 1  # Exactly representable in browser Number, checked before conversion.
MAX_U32 = 2**32 - 1
MAX_SEQ = 2**31 - 1
HEADER = struct.Struct("<4sBBHQQIIIHH")  # 40 bytes
PLAYER = struct.Struct("<HHHBhBI")  # 14 bytes
MAX_FRAME = HEADER.size + MAX_PLAYERS * PLAYER.size + (MAX_CELLS + 3) // 4
PHASES = ("waiting", "playing", "finished")
# Each byte expands to four cells. Cache this small table for native/load readers.
PAINT_TEXT = tuple("".join(str((byte >> shift) & 3) for shift in (0, 2, 4, 6)) for byte in range(256))


class WireError(ValueError):
    pass


def bounded(value, low, high, name):
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise WireError(f"{name} outside supported range")
    return value


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise WireError(f"{name} outside supported integer range")
    return value


def pack_paint(paint):
    if not 1 <= len(paint) <= MAX_CELLS:
        raise WireError("paint cell count outside supported range")
    packed = bytearray((len(paint) + 3) // 4)
    for i, colour in enumerate(paint):
        value = ord(colour) - 48 if isinstance(colour, str) else colour - 48
        if value not in (0, 1, 2):
            raise WireError("invalid paint colour")
        packed[i // 4] |= value << ((i % 4) * 2)
    return bytes(packed)


def unpack_paint(packed, count):
    integer(count, 1, MAX_CELLS, "paint cells")
    if len(packed) != (count + 3) // 4:
        raise WireError("paint length mismatch")
    if count % 4 and packed[-1] >> ((count % 4) * 2):
        raise WireError("nonzero paint padding")
    paint = "".join(PAINT_TEXT[value] for value in packed)[:count]
    if "3" in paint:
        raise WireError("invalid paint colour")
    return paint


@dataclass(frozen=True)
class Packet:
    revision: int
    metadata: str
    frame: bytes


class Encoder:
    def __init__(self):
        self.revision = 0
        self.slots = {}
        self.signature = None
        self.metadata_json = ""

    def packet(self, world):
        config = world.config
        players = list(world.players.values())
        if len(players) > MAX_PLAYERS:
            raise WireError("too many players")
        dimensions = [config.width, config.height, config.player_size, config.cell_size]
        signature = (tuple(dimensions), config.physics_hz, tuple((p.id, p.nickname) for p in players))
        if signature != self.signature:
            revision = integer(self.revision + 1, 1, MAX_U64, "roster revision")
            live = {p.id for p in players}
            slots = {identity: slot for identity, slot in self.slots.items() if identity in live}
            free = iter(sorted(set(range(1, MAX_PLAYERS + 1)) - set(slots.values())))
            for player in players:
                if player.id not in slots:
                    slots[player.id] = next(free)
            metadata = {
                "type": "metadata",
                "v": VERSION,
                "revision": str(revision),
                "world": dimensions,
                "physics_hz": config.physics_hz,
                "players": [[slots[p.id], p.id, p.nickname] for p in players],
            }
            # Validate the same bounds as receivers before caching an immutable roster.
            Decoder().metadata(metadata)
            self.revision, self.slots, self.signature = revision, slots, signature
            self.metadata_json = json.dumps(metadata, separators=(",", ":"), ensure_ascii=True)
        tick = integer(world.tick, 0, MAX_TICK, "tick")
        round_number = integer(world.round, 0, MAX_U32, "round")
        remaining = round(bounded(world.remaining, 0, MAX_U32 / 1000, "remaining") * 1000)
        intermission = round(
            bounded(
                max(0, world.intermission) if world.phase == "finished" else 0,
                0,
                MAX_U32 / 1000,
                "intermission",
            )
            * 1000
        )
        if world.phase not in PHASES:
            raise WireError("unknown phase")
        frame = bytearray(
            HEADER.pack(
                b"MBX2",
                VERSION,
                PHASES.index(world.phase),
                len(players),
                self.revision,
                tick,
                round_number,
                remaining,
                intermission,
                len(world.paint),
                0,
            )
        )
        for p in players:
            x = round((bounded(p.body.position.x, -128, 3967.9375, "x") + 128) * 16)
            y = round((bounded(p.body.position.y, -128, 3967.9375, "y") + 128) * 16)
            bounded(p.body.angle, -float("1e308"), float("1e308"), "angle")
            angle = round((p.body.angle % math.tau) * 256 / math.tau) % 256
            vy = round(bounded(p.body.velocity.y, -4096, 4095.875, "vy") * 8)
            integer(p.team, 1, 2, "team")
            if type(p.jump_ready) is not bool:
                raise WireError("invalid jump flag")
            integer(p.seq, -1, MAX_SEQ, "input acknowledgement")
            seq = MAX_U32 if p.seq == -1 else p.seq
            frame.extend(
                PLAYER.pack(self.slots[p.id], x, y, angle, vy, p.team | (int(p.jump_ready) << 2), seq)
            )
        frame.extend(pack_paint(world.paint))
        return Packet(self.revision, self.metadata_json, bytes(frame))


class Decoder:
    def __init__(self):
        self.revision = 0
        self.roster = {}
        self.world = None
        self.signature = None
        self.last_tick = -1

    def metadata(self, message):
        if not isinstance(message, dict) or set(message) != {
            "type",
            "v",
            "revision",
            "world",
            "physics_hz",
            "players",
        }:
            raise WireError("invalid metadata fields")
        if message["type"] != "metadata" or type(message["v"]) is not int or message["v"] != VERSION:
            raise WireError("unsupported metadata version")
        revision = message["revision"]
        if (
            not isinstance(revision, str)
            or not revision.isascii()
            or not revision.isdecimal()
            or not revision
            or revision[0] == "0"
            or len(revision) > 20
        ):
            raise WireError("invalid roster revision")
        revision = integer(int(revision), 1, MAX_U64, "roster revision")
        dimensions = message["world"]
        if (
            not isinstance(dimensions, list)
            or len(dimensions) != 4
            or any(type(v) is not int for v in dimensions)
            or dimensions[:3] != [1200, 720, 24]
            or dimensions[3] not in (12, 24, 40, 60)
            or type(message["physics_hz"]) is not int
            or message["physics_hz"] != 60
        ):
            raise WireError("unsupported world constants")
        rows = message["players"]
        if not isinstance(rows, list) or len(rows) > MAX_PLAYERS:
            raise WireError("invalid roster length")
        roster = {}
        identities = set()
        for row in rows:
            if not isinstance(row, list) or len(row) != 3:
                raise WireError("invalid roster row")
            slot, identity, name = row
            integer(slot, 1, MAX_PLAYERS, "wire slot")
            if not isinstance(identity, str) or not 1 <= len(identity) <= 64 or not identity.isprintable():
                raise WireError("invalid identity")
            if not isinstance(name, str) or not 1 <= len(name) <= 24 or not name.isprintable():
                raise WireError("invalid nickname")
            if slot in roster or identity in identities:
                raise WireError("duplicate roster slot/identity")
            roster[slot] = (identity, name)
            identities.add(identity)
        signature = (tuple(dimensions), tuple(sorted(roster.items())))
        if revision < self.revision:
            return False
        if revision == self.revision:
            if signature != self.signature:
                raise WireError("conflicting metadata revision")
            return False
        self.revision, self.roster, self.world, self.signature = revision, roster, dimensions[:], signature
        return True

    def frame(self, raw):
        if not isinstance(raw, (bytes, bytearray, memoryview)) or not HEADER.size <= len(raw) <= MAX_FRAME:
            raise WireError("invalid frame length/type")
        (
            magic,
            version,
            phase,
            count,
            revision,
            tick,
            round_number,
            remaining,
            intermission,
            cells,
            reserved,
        ) = HEADER.unpack_from(raw)
        if (
            magic != b"MBX2"
            or version != VERSION
            or phase >= len(PHASES)
            or reserved
            or not 0 <= count <= MAX_PLAYERS
            or revision == 0
            or not 1 <= cells <= MAX_CELLS
        ):
            raise WireError("invalid frame header")
        if len(raw) != HEADER.size + count * PLAYER.size + (cells + 3) // 4:
            raise WireError("frame length mismatch")
        integer(tick, 0, MAX_TICK, "tick")
        if not self.revision or revision > self.revision:
            raise WireError("matching metadata required")
        if revision < self.revision:
            return None
        if count != len(self.roster) or cells != self.world[0] * self.world[1] // self.world[3] ** 2:
            raise WireError("frame does not contain complete roster/grid")
        rows = []
        seen = set()
        for i in range(count):
            slot, x, y, angle, vy, flags, seq = PLAYER.unpack_from(raw, HEADER.size + i * PLAYER.size)
            if slot not in self.roster or slot in seen or flags & ~7 or flags & 3 not in (1, 2):
                raise WireError("unknown/duplicate player or invalid flags")
            if seq != MAX_U32:
                integer(seq, 0, MAX_SEQ, "input acknowledgement")
            identity, name = self.roster[slot]
            seen.add(slot)
            rows.append(
                [
                    identity,
                    name,
                    flags & 3,
                    x / 16 - 128,
                    y / 16 - 128,
                    angle * math.tau / 256,
                    vy / 8,
                    bool(flags & 4),
                    -1 if seq == MAX_U32 else seq,
                ]
            )
        paint = unpack_paint(raw[HEADER.size + count * PLAYER.size :], cells)
        if tick <= self.last_tick:
            return None
        self.last_tick = tick
        return {
            "type": "state",
            "v": VERSION,
            "tick": tick,
            "t": tick / 60,
            "round": round_number,
            "phase": PHASES[phase],
            "remaining": remaining / 1000,
            "next_round_in": intermission / 1000,
            "world": self.world[:],
            "paint": paint,
            "coverage": [round(paint.count(str(i)) * 100 / cells, 2) for i in range(3)],
            "players": rows,
            "metadata_revision": str(revision),
        }
