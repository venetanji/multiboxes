"""Optional Pygame client for the SAME WebSocket/Pymunk world as the browser.

Install with `pip install -e '.[native]'`, then `python -m multibox.game_client`.
The OSC/Zeroconf path is superseded; no per-client UDP listener is required.
"""

import argparse
import asyncio
import json

import pygame
from websockets.asyncio.client import connect

from .player import Player
from .wire import Decoder

COLOURS = [(166, 173, 162), (32, 35, 31), (250, 250, 245)]
KEYS = {
    pygame.K_LEFT: "left",
    pygame.K_a: "left",
    pygame.K_RIGHT: "right",
    pygame.K_d: "right",
    pygame.K_UP: "jump",
    pygame.K_w: "jump",
    pygame.K_SPACE: "jump",
    pygame.K_DOWN: "down",
    pygame.K_s: "down",
}


def draw_state(screen, state, you, objects):
    """Render full state and delete departed players instead of leaving ghosts."""
    w, h, size, cell = state["world"]
    arena = screen.subsurface((0, 54, w, h))
    arena.fill(COLOURS[0])
    for index, colour in enumerate(state["paint"]):
        if colour != "0":
            pygame.draw.rect(
                arena,
                COLOURS[int(colour)],
                (index % (w // cell) * cell, index // (w // cell) * cell, cell, cell),
            )
    live = {row[0] for row in state["players"]}
    for player_id in set(objects) - live:
        del objects[player_id]
    for row in sorted(state["players"], key=lambda row: row[0] == you):
        if row[0] not in objects:
            objects[row[0]] = Player(row[3], row[4])
        player = objects[row[0]]
        player.id, player.team, player.local, player.size = row[0], row[2], row[0] == you, size
        player.set_position(row[3], row[4])
        player.set_rotation(row[5])
        player.draw(arena)
    screen.fill((238, 237, 231), (0, 0, w, 54))
    coverage = state["coverage"]
    label = (
        f"BLACK {coverage[1]:.1f}%    |    {state['phase'].upper()} {state['remaining']:.0f}s"
        f"    |    WHITE {coverage[2]:.1f}%    |    {len(live)} players    |    pink = YOU"
    )
    screen.blit(pygame.font.Font(None, 26).render(label, True, COLOURS[1]), (16, 17))


async def receive_state(ws, decoder):
    while True:
        raw = await ws.recv()
        if isinstance(raw, str):
            if len(raw) > 65536:
                raise ValueError("server metadata too large")
            decoder.metadata(json.loads(raw))
        else:
            state = decoder.frame(raw)
            if state is not None:
                return state


async def run_client(server, nickname, *, max_frames=None, screenshot=None):
    pygame.init()
    receiver = None
    try:
        async with connect(server, max_size=131072, max_queue=2, compression=None) as ws:
            await ws.send(json.dumps({"type": "join", "v": 2, "nickname": nickname}))
            welcome = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
            if welcome.get("type") != "welcome" or welcome.get("v") != 2:
                raise ValueError("expected Multiboxes v2 welcome")
            you, decoder = welcome["you"], Decoder()
            state = await asyncio.wait_for(receive_state(ws, decoder), timeout=8)
            screen = pygame.display.set_mode((state["world"][0], state["world"][1] + 54))
            pygame.display.set_caption(
                "Multiboxes · Black / White · arrows/WASD, up jumps, down paints faster"
            )
            held, objects, seq = set(), {}, 0

            async def receive():
                nonlocal state
                while True:
                    state = await receive_state(ws, decoder)

            receiver = asyncio.create_task(receive())
            last_send, frames, running = 0, 0, True

            async def send_buttons():
                nonlocal seq, last_send
                buttons = set(KEYS[key] for key in held)
                await ws.send(
                    json.dumps(
                        {
                            "type": "input",
                            "seq": seq,
                            **{key: key in buttons for key in ("left", "right", "jump", "down")},
                        }
                    )
                )
                seq += 1
                last_send = asyncio.get_running_loop().time()

            while running and (max_frames is None or frames < max_frames):
                if receiver.done():
                    await receiver
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (
                        event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
                    ):
                        running = False
                    elif event.type == pygame.WINDOWFOCUSLOST:
                        held.clear()
                        await send_buttons()
                    elif event.type in (pygame.KEYDOWN, pygame.KEYUP) and event.key in KEYS:
                        before = set(held)
                        if event.type == pygame.KEYDOWN:
                            if getattr(event, "repeat", False):
                                continue
                            held.add(event.key)
                        else:
                            held.discard(event.key)
                        # Preserve a press/release occurring in the same render frame.
                        if before != held:
                            await send_buttons()
                now = asyncio.get_running_loop().time()
                if now - last_send >= 0.05:
                    await send_buttons()
                draw_state(screen, state, you, objects)
                pygame.display.flip()
                frames += 1
                await asyncio.sleep(1 / 60)
            if screenshot:
                pygame.image.save(screen, screenshot)
            await ws.send(
                json.dumps(
                    {"type": "input", "seq": seq, "left": False, "right": False, "jump": False, "down": False}
                )
            )
    finally:
        if receiver:
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="ws://localhost:8000/ws")
    parser.add_argument("--nickname", default="Box")
    args = parser.parse_args()
    try:
        asyncio.run(run_client(args.server, args.nickname))
    except (OSError, ValueError, TimeoutError, ConnectionError) as error:
        parser.exit(1, f"Could not play: {error}\nCheck the server URL and start the server first.\n")


if __name__ == "__main__":
    main()
