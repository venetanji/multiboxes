// Pure helpers shared by browser code and Node's built-in test runner.
export function serverUrl(value, location) {
  const candidate =
    value.trim() ||
    `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`;
  let url;
  try {
    url = new URL(candidate);
  } catch {
    throw new Error(
      "Enter a full ws:// or wss:// server URL, including port and path.",
    );
  }
  if (
    !["ws:", "wss:"].includes(url.protocol) ||
    !url.hostname ||
    url.username ||
    url.password ||
    url.hash
  )
    throw new Error(
      "Use ws:// or wss:// with a hostname/IP, port and path. Credentials and fragments are not supported.",
    );
  if (location.protocol === "https:" && url.protocol !== "wss:")
    throw new Error(
      "This HTTPS page needs WSS with a valid certificate. For localhost, open the client at http://localhost:8000 instead.",
    );
  return url.href;
}

export class HeldInput {
  sources = new Map();
  set(source, button, pressed) {
    const before = JSON.stringify(this.buttons());
    if (pressed) this.sources.set(source, button);
    else this.sources.delete(source);
    return before !== JSON.stringify(this.buttons());
  }
  buttons() {
    const values = new Set(this.sources.values());
    return Object.fromEntries(
      ["left", "right", "jump", "down"].map((key) => [key, values.has(key)]),
    );
  }
  clear() {
    this.sources.clear();
  }
}

export function interpolatePlayers(before, after, fraction) {
  if (!before || before.round !== after.round) return after.players;
  const previous = new Map(before.players.map((row) => [row[0], row]));
  const f = Math.max(0, Math.min(1, fraction));
  return after.players.map((row) => {
    const old = previous.get(row[0]);
    if (!old) return row;
    const result = [...row];
    for (const i of [3, 4]) result[i] = old[i] + (row[i] - old[i]) * f;
    const delta = Math.atan2(
      Math.sin(row[5] - old[5]),
      Math.cos(row[5] - old[5]),
    );
    result[5] = old[5] + delta * f;
    return result;
  });
}

export function validState(s) {
  if (
    !s ||
    s.type !== "state" ||
    s.v !== 2 ||
    !Number.isInteger(s.tick) ||
    !Number.isFinite(s.t) ||
    !Number.isInteger(s.round) ||
    !["waiting", "playing", "finished"].includes(s.phase) ||
    !Number.isFinite(s.remaining) ||
    !Number.isFinite(s.next_round_in)
  )
    return false;
  const w = s.world;
  if (
    !Array.isArray(w) ||
    w.length !== 4 ||
    w[0] !== 1200 ||
    w[1] !== 720 ||
    w[2] !== 24 ||
    ![12, 24, 40, 60].includes(w[3])
  )
    return false;
  if (
    typeof s.paint !== "string" ||
    s.paint.length !== (w[0] * w[1]) / w[3] ** 2 ||
    /[^012]/.test(s.paint)
  )
    return false;
  if (
    !Array.isArray(s.coverage) ||
    s.coverage.length !== 3 ||
    !s.coverage.every((n) => Number.isFinite(n) && n >= 0 && n <= 100)
  )
    return false;
  if (!Array.isArray(s.players) || s.players.length > 200) return false;
  const ids = new Set();
  return s.players.every((row) => {
    if (
      !Array.isArray(row) ||
      row.length !== 9 ||
      typeof row[0] !== "string" ||
      row[0].length > 64 ||
      ids.has(row[0]) ||
      typeof row[1] !== "string" ||
      row[1].length > 48 ||
      ![1, 2].includes(row[2]) ||
      !row.slice(3, 7).every(Number.isFinite) ||
      typeof row[7] !== "boolean" ||
      !Number.isInteger(row[8])
    )
      return false;
    ids.add(row[0]);
    return true;
  });
}
