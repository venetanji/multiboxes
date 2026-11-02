"""Single-world HTTP/WebSocket adapter for the original Pymunk physics game.

Run `python -m multibox.game_server`, then open http://localhost:8000.
No Pygame or OSC dependency is needed on the server. Never run multiple workers:
process-local worlds would give different students different games.
"""

import argparse
import asyncio
from collections import deque
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
import hmac
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import uvicorn

from .protocol import MAX_MESSAGE_BYTES, ProtocolError, RateLimiter, decode, parse_input, parse_join
from .simulation import Config, World


@dataclass(eq=False)
class Peer:
    ws: WebSocket
    player_id: str | None = None
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1))
    active: bool = True


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return {"p50": 0, "p95": 0, "p99": 0, "max": 0}
    return {key: round(ordered[min(len(ordered)-1, int((len(ordered)-1)*p))], 3)
            for key, p in (("p50", 0.5), ("p95", 0.95), ("p99", 0.99), ("max", 1))}


class Hub:
    def __init__(self, world: World, *, send_timeout: float = 1):
        self.world, self.send_timeout = world, send_timeout
        self.peers: set[Peer] = set()
        self.tick_lag = deque(maxlen=7200)
        self.step_time = deque(maxlen=7200)
        self.queue_max = self.queue_replacements = self.slow_disconnects = 0
        self.snapshots = self.sent_bytes = self.sent_states = 0
        self.discarded_lag = 0.0

    def metrics(self):
        return {"tick": self.world.tick, "players": len(self.world.players), "sessions": len(self.peers),
                "tick_lag_ms": distribution(self.tick_lag), "step_ms": distribution(self.step_time),
                "discarded_lag_seconds": round(self.discarded_lag, 4),
                "queue_max": self.queue_max, "queue_replacements": self.queue_replacements,
                "slow_disconnects": self.slow_disconnects, "snapshots": self.snapshots,
                "sent_bytes": self.sent_bytes, "sent_states": self.sent_states,
                "paint_writes": self.world.paint_writes, "jumps": self.world.jumps}

    def publish(self):
        # One serialization for everybody. Every queued object is the SAME string.
        state = json.dumps(self.world.snapshot(), separators=(",", ":"), ensure_ascii=True)
        self.snapshots += 1
        for peer in self.peers:
            if not peer.player_id or not peer.active:
                continue
            if peer.queue.full():
                peer.queue.get_nowait()
                self.queue_replacements += 1
            peer.queue.put_nowait(state)
            self.queue_max = max(self.queue_max, peer.queue.qsize())

    async def close(self, peer: Peer, *, code=1001, reason="session closed"):
        if not peer.active:
            return
        peer.active = False
        self.peers.discard(peer)
        if peer.player_id:
            self.world.remove_player(peer.player_id)
        with suppress(TimeoutError, RuntimeError, OSError, WebSocketDisconnect):
            await asyncio.wait_for(peer.ws.close(code=code, reason=reason), timeout=0.25)

    async def send(self, peer: Peer):
        try:
            while peer.active:
                state = await peer.queue.get()
                await asyncio.wait_for(peer.ws.send_text(state), timeout=self.send_timeout)
                self.sent_bytes += len(state)  # ensure_ascii means characters == UTF-8 bytes.
                self.sent_states += 1
        except TimeoutError:
            self.slow_disconnects += 1
            await self.close(peer, reason="slow consumer; reconnect for full state")
        except (OSError, RuntimeError, WebSocketDisconnect):
            await self.close(peer)

    async def expire(self, now):
        expired = [peer for peer in self.peers if peer.player_id and
                   now - self.world.players[peer.player_id].input_at > self.world.config.idle_timeout]
        if expired:
            await asyncio.gather(*(self.close(peer, reason="input heartbeat expired") for peer in expired))

    async def maintain(self):
        # Socket closing can wait on a transport. Keep it outside the physics task.
        while True:
            await asyncio.sleep(0.25)
            await self.expire(asyncio.get_running_loop().time())

    async def run(self):
        loop = asyncio.get_running_loop()
        interval = 1 / self.world.config.physics_hz
        next_tick = loop.time()
        snapshot_every = self.world.config.physics_hz // self.world.config.snapshot_hz
        while True:
            await asyncio.sleep(max(0, next_tick - loop.time()))
            now = loop.time()
            self.tick_lag.append(max(0, now - next_tick) * 1000)
            self.world.step(now)
            self.step_time.append((loop.time() - now) * 1000)
            if self.world.tick % snapshot_every == 0:
                self.publish()
            next_tick += interval
            # Bound catch-up work, record lost time rather than silently slowing down.
            if loop.time() - next_tick > interval * 5:
                self.discarded_lag += loop.time() - next_tick
                next_tick = loop.time()


def origin_allowed(ws, allowed_origins):
    origin = ws.headers.get("origin")
    if origin is None:  # Native clients have no browser Origin; no browser account/cookies exist.
        return True
    if origin in allowed_origins:
        return True
    parsed = urlsplit(origin)
    return (parsed.scheme in ("http", "https") and parsed.netloc.lower() == ws.headers.get("host", "").lower()
            and not parsed.path and not parsed.query and not parsed.fragment and not parsed.username)


def create_app(config: Config | None = None, *, teacher_token: str | None = None,
               allowed_origins: tuple[str, ...] = (), join_timeout: float = 5) -> FastAPI:
    hub = Hub(World(config))

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(hub.run(), name="multibox-world")
        maintenance = asyncio.create_task(hub.maintain(), name="multibox-expiry")
        app.state.world_task = task
        try:
            yield
        finally:
            task.cancel()
            maintenance.cancel()
            await asyncio.gather(task, maintenance, return_exceptions=True)
            await asyncio.gather(*(hub.close(peer, reason="server shutdown") for peer in list(hub.peers)))

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.hub = hub

    @app.get("/health")
    async def health():
        if app.state.world_task.done():
            raise HTTPException(503, "world stopped")
        return {"ok": True, "players": len(hub.world.players), "tick": hub.world.tick}

    def require_teacher(request):
        if not teacher_token:
            raise HTTPException(404)
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied.encode(), f"Bearer {teacher_token}".encode()):
            raise HTTPException(401, "teacher bearer token required")

    @app.get("/admin/metrics")
    async def metrics(request: Request):
        require_teacher(request)
        return hub.metrics()

    @app.post("/admin/round")
    async def round_control(request: Request):
        require_teacher(request)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_MESSAGE_BYTES:
                raise HTTPException(413)
        try:
            message = decode(body.decode("utf-8"))
            if set(message) != {"action"} or message["action"] not in ("start", "reset"):
                raise ProtocolError("expected start or reset")
        except (ProtocolError, UnicodeError) as error:
            raise HTTPException(400, str(error)) from error
        hub.world.reset_round(start=message["action"] == "start")
        return {"round": hub.world.round, "phase": hub.world.phase}

    @app.websocket("/ws")
    async def websocket(ws: WebSocket):
        if not origin_allowed(ws, allowed_origins):
            await ws.close(code=1008, reason="origin not allowed")
            return
        if len(hub.peers) >= hub.world.config.max_players:
            await ws.close(code=1013, reason="world full")
            return
        peer = Peer(ws)
        hub.peers.add(peer)  # Reserve before the first await, including unfinished joins.
        sender = None
        try:
            await ws.accept()
            raw = await asyncio.wait_for(ws.receive_text(), timeout=join_timeout)
            name = parse_join(decode(raw))
            loop = asyncio.get_running_loop()
            player = hub.world.add_player(name, now=loop.time())
            peer.player_id = player.id
            await asyncio.wait_for(ws.send_json({"type": "welcome", "v": 1, "you": player.id,
                                               "state": hub.world.snapshot()}), timeout=hub.send_timeout)
            sender = asyncio.create_task(hub.send(peer), name=f"send-{player.id}")
            limiter = RateLimiter(now=loop.time())
            while peer.active:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=hub.world.config.idle_timeout)
                if not limiter.allow(loop.time()):
                    raise ProtocolError("input rate exceeded")
                seq, buttons = parse_input(decode(raw))
                if seq <= player.seq:
                    raise ProtocolError("seq must increase")
                hub.world.set_input(player.id, buttons, now=loop.time(), seq=seq)
        except (ProtocolError, ValueError, KeyError) as error:
            await hub.close(peer, code=1008, reason=str(error)[:100])
        except TimeoutError:
            await hub.close(peer, reason="join/input timeout")
        except (WebSocketDisconnect, OSError, RuntimeError):
            pass
        finally:
            if sender:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
            await hub.close(peer)

    app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="client")
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--max-players", type=int, default=160)
    parser.add_argument("--round-seconds", type=float, default=180)
    args = parser.parse_args()
    origins = tuple(x.strip().rstrip("/") for x in os.getenv("MULTIBOX_ALLOWED_ORIGINS", "").split(",") if x.strip())
    app = create_app(Config(max_players=args.max_players, round_seconds=args.round_seconds),
                     teacher_token=os.getenv("MULTIBOX_TEACHER_TOKEN"), allowed_origins=origins)
    uvicorn.run(app, host=args.host, port=args.port, workers=1, ws="websockets", ws_max_size=MAX_MESSAGE_BYTES,
                ws_max_queue=4, ws_per_message_deflate=False, ws_ping_interval=10, ws_ping_timeout=10,
                access_log=False)


if __name__ == "__main__":
    main()
