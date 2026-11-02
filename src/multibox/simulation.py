"""The shared Pymunk world. No sockets, rendering, accounts or database here.

Coordinates follow Canvas/Pygame: positive y points DOWN. Input describes held
buttons; only this fixed-step world applies forces. Read Config for tutorial rules.
"""

from dataclasses import dataclass, field
import math

import pymunk


@dataclass(frozen=True)
class Config:
    width: int = 1200
    height: int = 720
    cell_size: int = 24
    player_size: int = 24
    max_players: int = 160
    physics_hz: int = 60
    snapshot_hz: int = 20
    gravity: float = 700
    move_acceleration: float = 1000
    down_acceleration: float = 1400
    jump_speed: float = 390
    max_speed_x: float = 300
    max_speed_y: float = 650
    paint_min_speed: float = 15
    input_timeout: float = 0.5
    idle_timeout: float = 30
    round_seconds: float = 180
    intermission_seconds: float = 10

    def __post_init__(self):
        if (
            self.round_seconds > (2**32 - 1) / 1000
            or self.intermission_seconds > (2**32 - 1) / 1000
            or self.max_speed_y > 4095.875
        ):
            raise ValueError("round/intermission or vertical speed exceeds wire bounds")
        if not (1 <= self.max_players <= 200):
            raise ValueError("max_players must be 1..200")
        if self.width != 1200 or self.height != 720 or self.player_size != 24:
            raise ValueError("this starter uses a 1200x720 world and 24px players")
        if self.cell_size not in (12, 24, 40, 60):
            raise ValueError("cell_size must divide the world, with at most 6000 cells")
        if self.physics_hz != 60 or self.snapshot_hz not in (10, 20, 30):
            raise ValueError("physics_hz must be 60; snapshot_hz must be 10, 20 or 30")
        for name in (
            "gravity",
            "move_acceleration",
            "down_acceleration",
            "jump_speed",
            "max_speed_x",
            "max_speed_y",
            "paint_min_speed",
            "input_timeout",
            "idle_timeout",
            "round_seconds",
            "intermission_seconds",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")


@dataclass(frozen=True)
class Input:
    left: bool = False
    right: bool = False
    jump: bool = False
    down: bool = False


@dataclass
class PlayerState:
    id: str
    nickname: str
    team: int  # 1 BLACK, 2 WHITE; 0 is unpainted territory.
    body: pymunk.Body
    shape: pymunk.Poly
    input: Input = field(default_factory=Input)
    input_at: float = 0
    seq: int = -1
    pending_jump: bool = False
    jump_latched: bool = False
    jump_ready: bool = False
    needs_separation: bool = False


class World:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.space = pymunk.Space()
        self.space.gravity = 0, self.config.gravity
        self.space.iterations = 12
        self.players: dict[str, PlayerState] = {}
        self.next_id = 1
        self.tick = 0
        self.time = 0.0
        self.round = 0
        self.remaining = self.config.round_seconds
        self.phase = "waiting"
        self.autostart = True
        self.intermission = 0.0
        self.paint = bytearray(b"0" * (self.columns * self.rows))
        self.counts = [len(self.paint), 0, 0]
        self.paint_writes = 0
        self.jumps = 0
        w, h = self.config.width, self.config.height
        self.walls = []
        for a, b in [((0, 0), (w, 0)), ((w, 0), (w, h)), ((w, h), (0, h)), ((0, h), (0, 0))]:
            wall = pymunk.Segment(self.space.static_body, a, b, 0)
            wall.friction = 0.8
            wall.elasticity = 0
            self.space.add(wall)
            self.walls.append(wall)

    @property
    def columns(self):
        return self.config.width // self.config.cell_size

    @property
    def rows(self):
        return self.config.height // self.config.cell_size

    def _spawn(self):
        # Sweep well-spaced slots across the upper world, checking live bodies.
        # A prime stride spreads simultaneous joins instead of stacking at one x.
        columns, rows, gap = 35, 17, 32
        for offset in range(columns * rows):
            slot = ((self.next_id - 1) * 37 + offset) % (columns * rows)
            x, y = 48 + slot % columns * gap, 48 + slot // columns * gap
            half = self.config.player_size / 2 + 2
            hits = self.space.bb_query(
                pymunk.BB(x - half, y - half, x + half, y + half), pymunk.ShapeFilter()
            )
            if not hits:
                return x, y
        raise ValueError("world full: no safe spawn")

    def add_player(self, nickname: str, *, now: float) -> PlayerState:
        if len(self.players) >= self.config.max_players:
            raise ValueError("world full")
        if self.next_id > 2**64 - 1:
            raise ValueError("identity counter exhausted; restart the world")
        spawn = self._spawn()
        if not self.players and self.phase == "waiting" and self.autostart:
            self.reset_round(start=True)
        black = sum(p.team == 1 for p in self.players.values())
        team = 1 if black <= len(self.players) - black else 2
        mass, size = 10, self.config.player_size
        body = pymunk.Body(mass, pymunk.moment_for_box(mass, (size, size)))
        body.position = spawn
        shape = pymunk.Poly.create_box(body, (size, size))
        shape.friction, shape.elasticity = 0.7, 0
        self.space.add(body, shape)
        player_id = f"p{self.next_id:06d}"
        self.next_id += 1
        player = PlayerState(player_id, nickname, team, body, shape, input_at=now)
        self.players[player_id] = player
        return player

    def remove_player(self, player_id: str):
        player = self.players.pop(player_id, None)
        if player:
            self.space.remove(player.shape, player.body)

    def set_input(self, player_id: str, buttons: Input, *, now: float, seq: int = -1):
        player = self.players[player_id]
        # Keep a short press even if its release arrives before the next tick.
        if buttons.jump and not player.jump_latched:
            player.pending_jump = True
        # Reset/stale input clears forces without inventing a physical release.
        player.jump_latched = buttons.jump
        player.input, player.input_at, player.seq = buttons, now, seq

    def _supported(self, player: PlayerState) -> bool:
        supported = False

        def contact(arbiter):
            nonlocal supported
            own_first = arbiter.shapes[0].body == player.body
            normal = arbiter.normal if own_first else -arbiter.normal
            # Side/ceiling bumps do not count. Inspect feet as well as the normal.
            if normal.y < 0.65:
                return
            for point in arbiter.contact_point_set.points:
                foot = point.point_a if own_first else point.point_b
                if foot.y > player.body.position.y + self.config.player_size * 0.15:
                    supported = True

        player.body.each_arbiter(contact)
        return supported

    def step(self, now: float):
        dt = 1 / self.config.physics_hz
        for player in self.players.values():
            if now - player.input_at > self.config.input_timeout:
                player.input = Input()
                player.pending_jump = False
            buttons, body = player.input, player.body
            if player.pending_jump and player.jump_ready:
                body.apply_impulse_at_world_point((0, -body.mass * self.config.jump_speed), body.position)
                player.jump_ready = False
                player.needs_separation = True
                self.jumps += 1
            player.pending_jump = False  # An airborne press is consumed, not buffered until landing.
            body.apply_force_at_world_point(
                (
                    (int(buttons.right) - int(buttons.left)) * self.config.move_acceleration * body.mass,
                    int(buttons.down) * self.config.down_acceleration * body.mass,
                ),
                body.position,
            )
            # Gentle horizontal/rotational damping; gravity remains physically integrated.
            body.velocity = body.velocity.x * 0.985, body.velocity.y
            body.angular_velocity *= 0.96

        self.space.step(dt)
        self.tick += 1
        self.time += dt
        for player in self.players.values():
            body = player.body
            body.velocity = (
                max(-self.config.max_speed_x, min(self.config.max_speed_x, body.velocity.x)),
                max(-self.config.max_speed_y, min(self.config.max_speed_y, body.velocity.y)),
            )
            supported = self._supported(player)
            if player.needs_separation:
                if not supported:
                    player.needs_separation = False
            elif supported and body.velocity.y >= -5:
                player.jump_ready = True
            elif not supported:
                player.jump_ready = False

        if self.phase == "playing":
            # All paints in a tick have a deterministic, rotating last-writer order.
            players = list(self.players.values())
            if players:
                pivot = self.tick % len(players)
                for player in players[pivot:] + players[:pivot]:
                    if player.body.velocity.y > self.config.paint_min_speed:
                        self._paint(player)
            self.remaining = max(0, self.remaining - dt)
            if self.remaining <= 1e-9:
                self.phase = "finished"
                self.intermission = self.config.intermission_seconds
        elif self.phase == "finished" and self.players:
            self.intermission -= dt
            if self.intermission <= 0:
                self.reset_round(start=True)

    def _paint(self, player: PlayerState):
        bb, cell = player.shape.bb, self.config.cell_size
        x0, x1 = max(0, int(bb.left // cell)), min(self.columns - 1, int(bb.right // cell))
        y0, y1 = max(0, int(bb.bottom // cell)), min(self.rows - 1, int(bb.top // cell))
        colour = ord(str(player.team))
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                index = y * self.columns + x
                previous = self.paint[index] - ord("0")
                if previous != player.team:
                    self.counts[previous] -= 1
                    self.counts[player.team] += 1
                    self.paint[index] = colour
                    self.paint_writes += 1

    def reset_round(self, *, start: bool):
        self.autostart = False  # An explicit teacher reset must stay waiting across all rejoins.
        self.round += 1
        self.paint[:] = b"0" * len(self.paint)
        self.counts = [len(self.paint), 0, 0]
        self.remaining = self.config.round_seconds
        self.phase = "playing" if start else "waiting"
        for player in self.players.values():
            player.input = Input()
            player.pending_jump = False
        # Bodies stay in place: a reset is safe even with a crowded live world.

    def snapshot(self) -> dict:
        return {
            "type": "state",
            "v": 1,
            "tick": self.tick,
            "t": round(self.time, 4),
            "round": self.round,
            "phase": self.phase,
            "remaining": round(self.remaining, 2),
            "next_round_in": round(max(0, self.intermission), 2) if self.phase == "finished" else 0,
            "world": [self.config.width, self.config.height, self.config.player_size, self.config.cell_size],
            "paint": self.paint.decode("ascii"),
            "coverage": [round(count * 100 / len(self.paint), 2) for count in self.counts],
            # Compact full rows: id, nickname, team, x, y, angle, vy, jump_ready, input_seq.
            "players": [
                [
                    p.id,
                    p.nickname,
                    p.team,
                    round(p.body.position.x, 2),
                    round(p.body.position.y, 2),
                    round(p.body.angle % math.tau, 3),
                    round(p.body.velocity.y, 1),
                    p.jump_ready,
                    p.seq,
                ]
                for p in self.players.values()
            ],
        }
