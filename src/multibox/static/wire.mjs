// Protocol v2. DataView makes every numeric offset and little-endian read explicit.
export const HEADER_BYTES = 40,
  PLAYER_BYTES = 14,
  MAX_FRAME = 4340;
const MAX_U64 = 18446744073709551615n,
  MAX_TICK = 9007199254740991n;
const phases = ["waiting", "playing", "finished"];
const fail = (message) => {
  throw new Error(message);
};

export function packPaint(paint) {
  if (
    typeof paint !== "string" ||
    paint.length < 1 ||
    paint.length > 6000 ||
    /[^012]/.test(paint)
  )
    fail("Invalid paint");
  const bytes = new Uint8Array(Math.ceil(paint.length / 4));
  for (let i = 0; i < paint.length; i++)
    bytes[i >> 2] |= Number(paint[i]) << ((i % 4) * 2);
  return bytes;
}
export function unpackPaint(bytes, count) {
  if (
    !Number.isInteger(count) ||
    count < 1 ||
    count > 6000 ||
    bytes.length !== Math.ceil(count / 4)
  )
    fail("Invalid paint length");
  if (count % 4 && bytes.at(-1) >> ((count % 4) * 2))
    fail("Invalid paint padding");
  const paint = [];
  for (let i = 0; i < count; i++) {
    const v = (bytes[i >> 2] >> ((i % 4) * 2)) & 3;
    if (v === 3) fail("Invalid paint colour");
    paint.push(String(v));
  }
  return paint.join("");
}

export class FrameDecoder {
  revision = 0n;
  roster = new Map();
  world = null;
  signature = null;
  lastTick = -1;
  metadata(m) {
    if (
      !m ||
      Object.keys(m).sort().join(",") !==
        "physics_hz,players,revision,type,v,world" ||
      m.type !== "metadata" ||
      m.v !== 2
    )
      fail("Unsupported metadata");
    if (
      typeof m.revision !== "string" ||
      !/^[1-9][0-9]{0,19}$/.test(m.revision)
    )
      fail("Invalid roster revision");
    const rev = BigInt(m.revision);
    if (rev > MAX_U64) fail("Invalid roster revision");
    const w = m.world;
    if (
      !Array.isArray(w) ||
      w.length !== 4 ||
      !w.every(Number.isInteger) ||
      w[0] !== 1200 ||
      w[1] !== 720 ||
      w[2] !== 24 ||
      ![12, 24, 40, 60].includes(w[3]) ||
      m.physics_hz !== 60
    )
      fail("Unsupported world constants");
    if (!Array.isArray(m.players) || m.players.length > 200)
      fail("Invalid roster length");
    const roster = new Map(),
      ids = new Set();
    for (const row of m.players) {
      if (!Array.isArray(row) || row.length !== 3) fail("Invalid roster row");
      const [slot, id, name] = row;
      if (
        !Number.isInteger(slot) ||
        slot < 1 ||
        slot > 200 ||
        roster.has(slot) ||
        typeof id !== "string" ||
        [...id].length < 1 ||
        [...id].length > 64 ||
        ids.has(id) ||
        /[\p{C}\p{Z}]/u.test(id.replaceAll(" ", ""))
      )
        fail("Invalid roster identity/slot");
      if (
        typeof name !== "string" ||
        [...name].length < 1 ||
        [...name].length > 24 ||
        /[\p{C}\p{Z}]/u.test(name.replaceAll(" ", ""))
      )
        fail("Invalid nickname");
      roster.set(slot, [id, name]);
      ids.add(id);
    }
    const signature = JSON.stringify([
      w,
      [...roster].sort((a, b) => a[0] - b[0]),
    ]);
    if (rev < this.revision) return false;
    if (rev === this.revision) {
      if (signature !== this.signature) fail("Conflicting metadata revision");
      return false;
    }
    this.revision = rev;
    this.roster = roster;
    this.world = [...w];
    this.signature = signature;
    return true;
  }
  frame(raw) {
    let bytes;
    if (raw instanceof ArrayBuffer) bytes = new Uint8Array(raw);
    else if (raw instanceof Uint8Array) bytes = raw;
    else fail("Invalid binary frame type");
    if (bytes.length < HEADER_BYTES || bytes.length > MAX_FRAME)
      fail("Invalid frame length");
    const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const phase = v.getUint8(5),
      count = v.getUint16(6, true),
      revision = v.getBigUint64(8, true),
      tick64 = v.getBigUint64(16, true),
      cells = v.getUint16(36, true);
    if (
      String.fromCharCode(...bytes.subarray(0, 4)) !== "MBX2" ||
      v.getUint8(4) !== 2 ||
      phase > 2 ||
      count > 200 ||
      revision === 0n ||
      cells < 1 ||
      cells > 6000 ||
      v.getUint16(38, true) !== 0
    )
      fail("Invalid frame header");
    if (
      bytes.length !==
        HEADER_BYTES + count * PLAYER_BYTES + Math.ceil(cells / 4) ||
      tick64 > MAX_TICK
    )
      fail("Invalid frame length/tick");
    if (this.revision === 0n || revision > this.revision)
      fail("Matching metadata required");
    if (revision < this.revision) return null;
    if (
      count !== this.roster.size ||
      cells !== (this.world[0] * this.world[1]) / this.world[3] ** 2
    )
      fail("Incomplete roster/grid");
    const rows = [],
      seen = new Set();
    for (let i = 0; i < count; i++) {
      const offset = HEADER_BYTES + i * PLAYER_BYTES,
        slot = v.getUint16(offset, true),
        flags = v.getUint8(offset + 9),
        ack = v.getUint32(offset + 10, true);
      if (
        !this.roster.has(slot) ||
        seen.has(slot) ||
        flags & ~7 ||
        ![1, 2].includes(flags & 3) ||
        (ack > 2147483647 && ack !== 4294967295)
      )
        fail("Invalid player record");
      const [id, name] = this.roster.get(slot);
      seen.add(slot);
      rows.push([
        id,
        name,
        flags & 3,
        v.getUint16(offset + 2, true) / 16 - 128,
        v.getUint16(offset + 4, true) / 16 - 128,
        (v.getUint8(offset + 6) * Math.PI * 2) / 256,
        v.getInt16(offset + 7, true) / 8,
        !!(flags & 4),
        ack === 4294967295 ? -1 : ack,
      ]);
    }
    const paint = unpackPaint(
        bytes.subarray(HEADER_BYTES + count * PLAYER_BYTES),
        cells,
      ),
      tick = Number(tick64);
    if (tick <= this.lastTick) return null;
    this.lastTick = tick;
    const counts = [0, 0, 0];
    for (const colour of paint) counts[Number(colour)]++;
    return {
      type: "state",
      v: 2,
      tick,
      t: tick / 60,
      round: v.getUint32(24, true),
      phase: phases[phase],
      remaining: v.getUint32(28, true) / 1000,
      next_round_in: v.getUint32(32, true) / 1000,
      world: [...this.world],
      paint,
      coverage: counts.map((n) => Math.round((n * 10000) / cells) / 100),
      players: rows,
      metadata_revision: revision.toString(),
    };
  }
}
