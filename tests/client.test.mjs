import { test } from "node:test";
import assert from "node:assert/strict";
import {
  serverUrl,
  HeldInput,
  interpolatePlayers,
  validState,
} from "../src/multibox/static/client-core.mjs";

test("full server URL, local default, IPv6 and mixed-content guidance", () => {
  assert.equal(
    serverUrl("", { protocol: "http:", host: "localhost:8000" }),
    "ws://localhost:8000/ws",
  );
  assert.equal(
    serverUrl(" wss://game.example.edu:8443/class/ws ", { protocol: "https:" }),
    "wss://game.example.edu:8443/class/ws",
  );
  assert.equal(
    serverUrl("ws://[::1]:8000/ws", { protocol: "http:" }),
    "ws://[::1]:8000/ws",
  );
  for (const url of [
    "http://localhost:8000",
    "127.0.0.1",
    "wss://user:pass@server/ws",
    "wss://server/ws#x",
  ])
    assert.throws(() => serverUrl(url, { protocol: "http:" }));
  assert.throws(
    () => serverUrl("ws://localhost:8000/ws", { protocol: "https:" }),
    /WSS|wss/,
  );
});

test("held input preserves multiple sources, repeat is not a fresh press, clear releases all", () => {
  const input = new HeldInput();
  assert.equal(input.set("ArrowUp", "jump", true), true);
  assert.equal(input.set("ArrowUp", "jump", true), false);
  input.set("touch-1", "jump", true);
  input.set("ArrowUp", "jump", false);
  assert.equal(input.buttons().jump, true);
  input.set("ArrowLeft", "left", true);
  input.clear();
  assert.deepEqual(input.buttons(), {
    left: false,
    right: false,
    jump: false,
    down: false,
  });
});

test("interpolation follows complete latest roster, shortest rotation and round reset", () => {
  const row = (id, x, a = 0) => [id, "Box", 1, x, 10, a, 0, true, 0];
  const a = { round: 1, players: [row("old", 0), row("same", 0, 6.2)] };
  const b = { round: 1, players: [row("same", 100, 0.1), row("new", 200)] };
  const result = interpolatePlayers(a, b, 0.5);
  assert.deepEqual(
    result.map((r) => r[0]),
    ["same", "new"],
  );
  assert.equal(result[0][3], 50);
  assert.ok(result[0][5] > 6.2 && result[0][5] < 6.4);
  assert.equal(interpolatePlayers(a, { ...b, round: 2 }, 0.5)[0][3], 100);
});

test("renderer rejects invalid full state rather than displaying a fake world", () => {
  const state = {
    type: "state",
    v: 2,
    tick: 0,
    t: 0,
    round: 1,
    phase: "playing",
    remaining: 180,
    next_round_in: 0,
    world: [1200, 720, 24, 24],
    paint: "0".repeat(1500),
    coverage: [100, 0, 0],
    players: [["p1", "Box", 1, 100, 100, 0, 0, false, 0]],
  };
  assert.ok(validState(state));
  assert.equal(validState({ ...state, paint: "2" }), false);
  assert.equal(validState({ ...state, world: [Infinity, 720, 24, 24] }), false);
  assert.equal(validState({ ...state, players: [["bad"]] }), false);
  assert.equal(
    validState({ ...state, players: Array(201).fill(state.players[0]) }),
    false,
  );
});
