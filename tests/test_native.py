import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")
from websockets.asyncio.server import serve

from multibox.game_client import draw_state, run_client
from multibox.simulation import World


def test_native_renders_team_colours_and_local_accent():
    pygame.init()
    try:
        world = World()
        player = world.add_player("native", now=0)
        screen = pygame.display.set_mode((1200, 774))
        draw_state(screen, world.snapshot(), player.id, {})
        x, y = map(int, player.body.position)
        assert screen.get_at((x + 16, y + 54))[:3] == (255, 56, 105)
    finally:
        pygame.quit()


async def test_native_joins_receives_full_state_and_sends_buttons():
    received = []
    world = World()
    player = world.add_player("native", now=0)

    async def handler(ws):
        received.append(json.loads(await ws.recv()))
        await ws.send(json.dumps({"type": "welcome", "v": 1, "you": player.id, "state": world.snapshot()}))
        async for raw in ws:
            received.append(json.loads(raw))

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        await run_client(f"ws://127.0.0.1:{port}/ws", "native", max_frames=5)
    assert received[0] == {"type": "join", "v": 1, "nickname": "native"}
    assert any(message.get("type") == "input" and message["jump"] is False for message in received[1:])


async def test_native_short_jump_edge_and_focus_loss_release_buttons():
    received = []
    world = World()
    player = world.add_player("native", now=0)

    async def handler(ws):
        await ws.recv()
        await ws.send(json.dumps({"type": "welcome", "v": 1, "you": player.id, "state": world.snapshot()}))
        phase = 0
        async for raw in ws:
            message = json.loads(raw)
            received.append(message)
            if phase == 0:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))
                pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_UP))
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT))
                phase = 1
            elif phase == 1 and message["right"]:
                pygame.event.post(pygame.event.Event(pygame.WINDOWFOCUSLOST))
                phase = 2
            elif phase == 2 and not message["right"]:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT, repeat=True))
                phase = 3

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        await run_client(f"ws://127.0.0.1:{port}/ws", "native", max_frames=20)
    assert any(message["jump"] for message in received)
    first_right = next(i for i, message in enumerate(received) if message["right"])
    assert any(not message["right"] for message in received[first_right + 1 :])
    released = next(i for i in range(first_right + 1, len(received)) if not received[i]["right"])
    assert all(not message["right"] for message in received[released:])
