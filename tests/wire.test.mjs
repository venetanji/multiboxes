import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  FrameDecoder,
  packPaint,
  unpackPaint,
} from "../src/multibox/static/wire.mjs";
const gold = JSON.parse(
  readFileSync(new URL("./fixtures/wire-v2.json", import.meta.url)),
);
const frame = () =>
  Uint8Array.from(
    Buffer.from(
      gold.header_hex +
        gold.player_hex +
        gold.paint_byte_hex.repeat(gold.paint_bytes),
      "hex",
    ),
  );

test("Python/JS golden frame with exact uint64 revision, max input ack and lifetime string identity", () => {
  const d = new FrameDecoder();
  d.metadata(gold.metadata);
  const s = d.frame(frame());
  const e = gold.expected;
  assert.deepEqual(s.players, [
    [e.id, e.nickname, e.team, e.x, e.y, e.angle, e.vy, e.jump, e.seq],
  ]);
  assert.equal(s.metadata_revision, "9007199254740993");
  assert.equal(s.remaining, e.remaining);
  assert.equal(s.paint, gold.paint_pattern.repeat(gold.paint_repeats));
  assert.deepEqual(s.coverage, e.coverage);
  assert.equal(s.tick, 60);
  assert.equal(s.round, 3);
  assert.equal(d.frame(frame()), null);
});
test("paint packing, padding and maximum sizes", () => {
  for (const n of [1, 2, 3, 4, 5, 1500, 6000]) {
    const paint = "0120".repeat(1500).slice(0, n),
      packed = packPaint(paint);
    assert.equal(packed.length, Math.ceil(n / 4));
    assert.equal(unpackPaint(packed, n), paint);
    if (n % 4) {
      packed[packed.length - 1] |= 1 << (2 * (n % 4));
      assert.throws(() => unpackPaint(packed, n));
    }
  }
  assert.deepEqual([...packPaint("0120")], [0x24]);
  assert.throws(() => packPaint("3"));
  assert.throws(() => packPaint("0".repeat(6001)));
});
test("malformed and truncated binary frames fail before rendering", () => {
  for (const [offset, bytes] of [
    [0, [0]],
    [4, [3]],
    [5, [255]],
    [6, [201, 0]],
    [8, Array(8).fill(0)],
    [36, [0, 0]],
    [38, [1, 0]],
    [40, [0, 0]],
    [49, [128]],
    [50, [0, 0, 0, 128]],
    [54, [3]],
  ]) {
    const b = frame();
    b.set(bytes, offset);
    const d = new FrameDecoder();
    d.metadata(gold.metadata);
    assert.throws(() => d.frame(b));
  }
  for (const b of [
    frame().slice(0, -1),
    new Uint8Array(frame().length + 1),
    new Uint8Array(10),
  ]) {
    const d = new FrameDecoder();
    d.metadata(gold.metadata);
    assert.throws(() => d.frame(b));
  }
});
test("metadata required, version conflicts rejected, stale revision never reuses a slot", () => {
  assert.throws(() => new FrameDecoder().frame(frame()), /metadata/);
  const d = new FrameDecoder();
  d.metadata(gold.metadata);
  d.frame(frame());
  const meta = structuredClone(gold.metadata);
  meta.revision = "9007199254740994";
  meta.players[0][1] = "new identity";
  d.metadata(meta);
  assert.equal(d.frame(frame()), null);
  const b = frame();
  new DataView(b.buffer).setBigUint64(8, 9007199254740994n, true);
  new DataView(b.buffer).setBigUint64(16, 61n, true);
  assert.equal(d.frame(b).players[0][0], "new identity");
  const bad = structuredClone(meta);
  bad.players[0][1] = "wrong";
  assert.throws(() => d.metadata(bad));
  for (const patch of [
    { v: 1 },
    { revision: "01" },
    { revision: "18446744073709551616" },
    {
      players: [
        [1, "a", "x"],
        [1, "b", "y"],
      ],
    },
    { world: [1200, 720, 24, 1] },
  ])
    assert.throws(() =>
      new FrameDecoder().metadata({ ...gold.metadata, ...patch }),
    );
});
