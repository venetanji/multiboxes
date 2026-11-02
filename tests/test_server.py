import asyncio
import json

from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from multibox.game_server import Hub, Peer, create_app
from multibox.simulation import Config, World


def join(ws, name="Box"):
    ws.send_json({"type": "join", "v": 1, "nickname": name})
    message = ws.receive_json()
    assert message["type"] == "welcome"
    assert len(message["state"]["paint"]) == 1500
    return message


def input_message(seq=0, **buttons):
    return {
        "type": "input",
        "seq": seq,
        "left": False,
        "right": False,
        "jump": False,
        "down": False,
    } | buttons


def test_join_inputs_disconnect_reconnect_full_snapshot_and_body_cleanup():
    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            welcome = join(ws)
            player_id = welcome["you"]
            ws.send_json(input_message(right=True))
            for _ in range(10):
                state = ws.receive_json()
                row = next(p for p in state["players"] if p[0] == player_id)
                if row[-1] == 0:
                    break
            assert row[-1] == 0
            assert client.get("/health").json()["players"] == 1
        assert client.get("/health").json()["players"] == 0
        assert len(app.state.hub.world.space.bodies) == 0
        with client.websocket_connect("/ws") as ws:
            welcome2 = join(ws)
            assert welcome2["you"] != player_id
            assert [p[0] for p in welcome2["state"]["players"]] == [welcome2["you"]]


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "join", "v": 1, "nickname": "again"},
        input_message(seq=0, team=2),
        input_message(seq=-1),
        {"type": "reset"},
    ],
)
def test_duplicate_join_or_invalid_input_closes_without_body_leak(bad):
    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            join(ws)
            ws.send_json(bad)
            with pytest.raises(WebSocketDisconnect) as closed:
                while True:
                    ws.receive_json()
            assert closed.value.code == 1008
        assert client.get("/health").json()["players"] == 0
        assert len(app.state.hub.world.space.bodies) == 0


def test_replayed_sequence_rejected():
    with TestClient(create_app()) as client:
        with client.websocket_connect("/ws") as ws:
            join(ws)
            ws.send_json(input_message(seq=2))
            ws.send_json(input_message(seq=2))
            with pytest.raises(WebSocketDisconnect):
                while True:
                    ws.receive_json()


def test_origin_is_explicit_and_full_world_rejects_extra_connection():
    app = create_app(Config(max_players=1), allowed_origins=("https://example.github.io",))
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws", headers={"origin": "https://evil.test"}):
                pass
        with client.websocket_connect("/ws", headers={"origin": "https://example.github.io"}) as ws:
            join(ws)
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws"):
                    pass


def test_unjoined_capacity_and_same_origin():
    with TestClient(create_app(Config(max_players=1))) as client:
        with client.websocket_connect("/ws", headers={"origin": "http://testserver"}):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws"):
                    pass


def test_teacher_controls_disabled_or_require_private_token():
    with TestClient(create_app()) as client:
        assert client.post("/admin/round", json={"action": "start"}).status_code == 404
    app = create_app(teacher_token="test-teacher-token")
    with TestClient(app) as client:
        assert client.post("/admin/round", json={"action": "start"}).status_code == 401
        headers = {"authorization": "Bearer test-teacher-token"}
        assert client.post("/admin/round", json={"action": "start"}, headers=headers).status_code == 200
        assert app.state.hub.world.phase == "playing"
        assert client.post("/admin/round", json={"action": "reset"}, headers=headers).status_code == 200
        assert app.state.hub.world.phase == "waiting"
        assert client.post("/admin/round", json={"action": "other"}, headers=headers).status_code == 400
        assert client.get("/admin/metrics", headers=headers).json()["queue_max"] == 0


class FakeSocket:
    def __init__(self, slow=False):
        self.slow, self.sent, self.closed = slow, [], False

    async def send_text(self, data):
        if self.slow:
            await asyncio.Event().wait()
        self.sent.append(json.loads(data))

    async def close(self, **kwargs):
        self.closed = True


async def test_slow_sender_does_not_block_world_and_queues_hold_latest_complete_state():
    hub = Hub(World(), send_timeout=0.08)
    slow, fast = Peer(FakeSocket(slow=True)), Peer(FakeSocket())
    for peer in (slow, fast):
        peer.player_id = hub.world.add_player("Box", now=asyncio.get_running_loop().time()).id
        hub.peers.add(peer)
    tasks = [
        asyncio.create_task(hub.run()),
        asyncio.create_task(hub.send(slow)),
        asyncio.create_task(hub.send(fast)),
    ]
    try:
        await asyncio.sleep(0.2)
        assert hub.world.tick >= 10
        assert slow.ws.closed
        assert len(hub.world.players) == 1
        assert len(fast.ws.sent) >= 3
        assert hub.metrics()["queue_max"] == 1
        assert all("paint" in state and "players" in state for state in fast.ws.sent)
        for _ in range(100):
            hub.publish()
        assert fast.queue.qsize() == 1
        assert hub.metrics()["queue_replacements"] >= 99
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_idle_expiry_removes_bodies_and_stops_inputs():
    hub = Hub(World(Config(idle_timeout=0.05)))
    peer = Peer(FakeSocket())
    peer.player_id = hub.world.add_player("idle", now=0).id
    hub.peers.add(peer)
    await hub.expire(now=1)
    assert peer.ws.closed
    assert not hub.world.players
    assert not hub.world.space.bodies


def test_join_timeout_and_oversized_binary_frames_release_reservations():
    app = create_app(join_timeout=0.01)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
        for frame in ("x" * 513, b"binary"):
            with client.websocket_connect("/ws") as ws:
                if isinstance(frame, bytes):
                    ws.send_bytes(frame)
                else:
                    ws.send_text(frame)
                with pytest.raises(WebSocketDisconnect):
                    ws.receive_json()
        assert not app.state.hub.peers
        assert not app.state.hub.world.players


def test_shared_serialization_is_one_object_and_newest_state_is_complete():
    hub = Hub(World())
    a, b = Peer(FakeSocket()), Peer(FakeSocket())
    for peer in (a, b):
        peer.player_id = hub.world.add_player("Box", now=0).id
        hub.peers.add(peer)
    hub.publish()
    assert a.queue.get_nowait() is b.queue.get_nowait()
    hub.world.step(0)
    hub.publish()
    hub.world.remove_player(a.player_id)
    a.player_id = None
    hub.world.reset_round(start=True)
    hub.publish()
    state = json.loads(b.queue.get_nowait())
    assert state["paint"] == "0" * 1500
    assert [p[0] for p in state["players"]] == [b.player_id]


async def test_transport_already_closed_during_cleanup_is_safe():
    import anyio

    class ClosedSocket(FakeSocket):
        async def close(self, **kwargs):
            raise anyio.ClosedResourceError

    hub = Hub(World())
    peer = Peer(ClosedSocket())
    peer.player_id = hub.world.add_player("closed", now=0).id
    hub.peers.add(peer)
    await hub.close(peer)
    assert not hub.world.players
    assert not hub.peers


def test_malformed_origin_rejected_without_server_error():
    with TestClient(create_app()) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws", headers={"origin": "http://[invalid"}):
                pass
