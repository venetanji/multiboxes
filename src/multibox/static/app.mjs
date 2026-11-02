import {
  serverUrl,
  HeldInput,
  interpolatePlayers,
  validState,
} from "./client-core.mjs";

const $ = (id) => document.getElementById(id);
const canvas = $("world"),
  ctx = canvas.getContext("2d");
const paintCanvas = document.createElement("canvas");
paintCanvas.width = 1200;
paintCanvas.height = 720;
const paintCtx = paintCanvas.getContext("2d");
const input = new HeldInput();
const colours = ["#a6ada2", "#20231f", "#fafaf5"];
const keyMap = {
  ArrowLeft: "left",
  KeyA: "left",
  ArrowRight: "right",
  KeyD: "right",
  ArrowUp: "jump",
  KeyW: "jump",
  Space: "jump",
  ArrowDown: "down",
  KeyS: "down",
};
let socket = null,
  you = null,
  frames = [],
  sequence = 0,
  heartbeat = null,
  timeout = null;
let spawnedAt = 0,
  lastPaint = null,
  lastReceive = 0;
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

function status(message, error = false) {
  if ($("status").textContent !== message) $("status").textContent = message;
  $("status").dataset.error = String(error);
}
function sendInput() {
  if (!you || socket?.readyState !== WebSocket.OPEN) return;
  if (socket.bufferedAmount > 2048) {
    disconnect("Connection is too slow. Reconnect to try again.", true);
    return;
  }
  socket.send(
    JSON.stringify({ type: "input", seq: sequence++, ...input.buttons() }),
  );
}
function clearInput() {
  input.clear();
  document
    .querySelectorAll("[data-control]")
    .forEach((button) => button.setAttribute("aria-pressed", "false"));
  sendInput();
}
function disconnect(
  message = "Disconnected. Connect to join again.",
  error = false,
) {
  const previous = socket;
  // Detach before clearing: a saturated buffer must not recurse through sendInput.
  if (
    you &&
    previous?.readyState === WebSocket.OPEN &&
    previous.bufferedAmount <= 2048
  )
    previous.send(
      JSON.stringify({
        type: "input",
        seq: sequence++,
        left: false,
        right: false,
        jump: false,
        down: false,
      }),
    );
  socket = null;
  you = null;
  frames = [];
  lastPaint = null;
  clearInput();
  clearInterval(heartbeat);
  clearTimeout(timeout);
  if (previous) previous.close(1000, "client disconnect");
  $("disconnect").hidden = true;
  $("connect").textContent = "Connect";
  $("empty").hidden = false;
  $("you").textContent = "Look for the pink outline + YOU";
  $("population").textContent = "0 players connected";
  $("black-score").textContent = $("white-score").textContent = "—";
  $("black-bar").style.width = $("white-bar").style.width = "0%";
  status(message, error);
}
function acceptState(state) {
  if (!validState(state))
    throw new Error("The server sent an invalid game snapshot.");
  if (frames.length && state.round !== frames.at(-1).round) frames = [];
  if (frames.length && state.tick < frames.at(-1).tick)
    throw new Error("The server sent an out-of-order snapshot.");
  frames.push(state);
  if (frames.length > 8) frames.shift();
  lastReceive = performance.now();
  const local = state.players.find((row) => row[0] === you);
  if (!local)
    throw new Error("Your session has expired. Reconnect to join again.");
  const team = local[2] === 1 ? "BLACK" : "WHITE";
  $("you").textContent =
    `YOU · ${team} · ${local[7] ? "jump ready" : "land to recharge"}`;
  $("population").textContent =
    `${state.players.length} player${state.players.length === 1 ? "" : "s"} connected`;
  $("black-score").textContent = `${state.coverage[1].toFixed(1)}%`;
  $("white-score").textContent = `${state.coverage[2].toFixed(1)}%`;
  $("black-bar").style.width = `${state.coverage[1]}%`;
  $("white-bar").style.width = `${state.coverage[2]}%`;
  const seconds = Math.ceil(
    state.phase === "finished" ? state.next_round_in : state.remaining,
  );
  $("timer").textContent = `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
  $("round-label").textContent =
    state.phase === "finished"
      ? "NEXT ROUND"
      : state.phase === "waiting"
        ? "WAITING"
        : `ROUND ${state.round}`;
  if (state.phase === "finished") {
    const winner =
      state.coverage[1] === state.coverage[2]
        ? "A draw"
        : `${state.coverage[1] > state.coverage[2] ? "BLACK" : "WHITE"} wins`;
    status(`${winner}. New round in ${seconds}s. Stack, jump and repaint.`);
  } else if (state.phase === "waiting")
    status("Waiting for the teacher to start a round.");
  else status(`Connected · ${team} team. Your square has the pink outline.`);
}
function connect(event) {
  event.preventDefault();
  disconnect("Connecting…");
  let url;
  try {
    url = serverUrl($("server").value, location);
  } catch (error) {
    status(error.message, true);
    return;
  }
  const name = $("nickname").value.trim();
  if (!name || name.length > 24 || /[\p{C}]/u.test(name)) {
    status("Use a nickname with 1–24 printable characters.", true);
    return;
  }
  $("server").value = url;
  try {
    localStorage.setItem("multibox-server", url);
    localStorage.setItem("multibox-nickname", name);
  } catch {}
  const current = new WebSocket(url);
  socket = current;
  sequence = 0;
  $("connect").textContent = "Connecting…";
  $("disconnect").hidden = false;
  timeout = setTimeout(() => {
    if (socket === current)
      disconnect(
        "Connection timed out. Check the server URL, network and certificate, then reconnect.",
        true,
      );
  }, 8000);
  current.onopen = () => {
    if (socket !== current) return;
    current.send(JSON.stringify({ type: "join", v: 1, nickname: name }));
  };
  current.onmessage = (event) => {
    if (socket !== current) return; // Late events from a switched URL cannot mutate this session.
    try {
      if (typeof event.data !== "string" || event.data.length > 131072)
        throw new Error("Unsupported server message.");
      const message = JSON.parse(event.data);
      if (
        message.type === "welcome" &&
        !you &&
        message.v === 1 &&
        typeof message.you === "string"
      ) {
        you = message.you;
        acceptState(message.state);
        clearTimeout(timeout);
        spawnedAt = performance.now();
        $("empty").hidden = true;
        $("connect").textContent = "Reconnect";
        canvas.focus({ preventScroll: true });
        heartbeat = setInterval(sendInput, 50);
        sendInput();
      } else if (message.type === "state" && you) acceptState(message);
      else
        throw new Error(
          "Unexpected server protocol. Use a Multiboxes v1 server.",
        );
    } catch (error) {
      disconnect(error.message, true);
    }
  };
  current.onerror = () => {
    if (socket === current)
      disconnect(
        "Could not connect. Check the URL, server, allowed origin and TLS certificate; then reconnect.",
        true,
      );
  };
  current.onclose = (event) => {
    if (socket === current)
      disconnect(
        `Connection closed${event.reason ? `: ${event.reason}` : ". Check the server and reconnect."}`,
        true,
      );
  };
}
$("connection").addEventListener("submit", connect);
$("disconnect").addEventListener("click", () => disconnect());
$("server").addEventListener("input", () =>
  disconnect("Server changed. Select Connect to join it."),
);
try {
  $("server").value =
    new URLSearchParams(location.search).get("server") ||
    localStorage.getItem("multibox-server") ||
    serverUrl("", location);
  $("nickname").value = localStorage.getItem("multibox-nickname") || "Box";
} catch {
  $("server").value = serverUrl("", location);
}

for (const type of ["keydown", "keyup"])
  window.addEventListener(type, (event) => {
    const button = keyMap[event.code];
    const editing = /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(
      event.target.tagName,
    );
    if (
      !button ||
      (type === "keydown" &&
        (editing ||
          event.repeat ||
          event.ctrlKey ||
          event.metaKey ||
          event.altKey))
    )
      return;
    if (type === "keyup" && editing) {
      if (input.set(event.code, button, false)) sendInput();
      return;
    }
    event.preventDefault();
    if (input.set(event.code, button, type === "keydown")) sendInput();
  });
window.addEventListener("blur", clearInput);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) clearInput();
});
document.addEventListener("focusin", (event) => {
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) clearInput();
});
window.addEventListener("pagehide", () => disconnect());
for (const button of document.querySelectorAll("[data-control]")) {
  button.setAttribute("aria-pressed", "false");
  button.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    button.setPointerCapture(event.pointerId);
    if (input.set(`pointer-${event.pointerId}`, button.dataset.control, true))
      sendInput();
    button.setAttribute("aria-pressed", "true");
  });
  for (const type of ["pointerup", "pointercancel", "lostpointercapture"])
    button.addEventListener(type, (event) => {
      if (
        input.set(`pointer-${event.pointerId}`, button.dataset.control, false)
      )
        sendInput();
      button.setAttribute("aria-pressed", "false");
    });
  // Keyboard and assistive-technology activation of the visible controls.
  button.addEventListener("keydown", (event) => {
    if (event.repeat) return;
    if (!["Space", "Enter"].includes(event.code)) return;
    event.preventDefault();
    if (
      input.set(
        `button-${button.dataset.control}`,
        button.dataset.control,
        true,
      )
    )
      sendInput();
    button.setAttribute("aria-pressed", "true");
  });
  button.addEventListener("keyup", (event) => {
    if (!["Space", "Enter"].includes(event.code)) return;
    event.preventDefault();
    if (
      input.set(
        `button-${button.dataset.control}`,
        button.dataset.control,
        false,
      )
    )
      sendInput();
    button.setAttribute("aria-pressed", "false");
  });
  button.addEventListener("blur", clearInput);
  button.addEventListener("contextmenu", (event) => event.preventDefault());
}

function drawPaint(state) {
  if (state.paint === lastPaint) return;
  const [w, h, , cell] = state.world,
    columns = w / cell;
  paintCtx.fillStyle = colours[0];
  paintCtx.fillRect(0, 0, w, h);
  for (let i = 0; i < state.paint.length; i++) {
    if (state.paint[i] === "0") continue;
    paintCtx.fillStyle = colours[Number(state.paint[i])];
    paintCtx.fillRect(
      (i % columns) * cell,
      Math.floor(i / columns) * cell,
      cell,
      cell,
    );
  }
  lastPaint = state.paint;
}
function drawPlayer(row, now) {
  const local = row[0] === you,
    size = 24;
  const screenScale = Math.max(1, 1200 / canvas.clientWidth);
  ctx.save();
  ctx.translate(row[3], row[4]);
  ctx.rotate(row[5]);
  ctx.fillStyle = colours[row[2]];
  ctx.strokeStyle = row[2] === 1 ? "#fafaf5" : "#20231f";
  ctx.lineWidth = 2;
  ctx.fillRect(-size / 2, -size / 2, size, size);
  ctx.strokeRect(-size / 2, -size / 2, size, size);
  if (local) {
    ctx.strokeStyle = "#20231f";
    ctx.lineWidth = 6 * screenScale;
    ctx.strokeRect(-16, -16, 32, 32);
    ctx.strokeStyle = "#ff3869";
    ctx.lineWidth = 3 * screenScale;
    ctx.strokeRect(-16, -16, 32, 32);
  }
  ctx.restore();
  if (local) {
    // Keep the label legible in CSS pixels when a phone scales down the world.
    const fontSize = Math.max(14, 12 * screenScale),
      labelWidth = fontSize * 3.5,
      labelHeight = fontSize * 1.5;
    const x = Math.max(
      labelWidth / 2 + 3,
      Math.min(1200 - labelWidth / 2 - 3, row[3]),
    );
    const top = Math.max(2, row[4] - 24 - labelHeight);
    ctx.fillStyle = "#20231f";
    ctx.fillRect(x - labelWidth / 2, top, labelWidth, labelHeight);
    ctx.fillStyle = "#ff6c91";
    ctx.textAlign = "center";
    ctx.font = `bold ${fontSize}px system-ui`;
    ctx.fillText("YOU", x, top + fontSize * 1.1);
    if (!reducedMotion && now - spawnedAt < 2500) {
      ctx.strokeStyle = "#ff3869";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(
        row[3],
        row[4],
        27 + ((now - spawnedAt) % 800) / 35,
        0,
        Math.PI * 2,
      );
      ctx.stroke();
    }
  }
}
function render(now) {
  ctx.fillStyle = colours[0];
  ctx.fillRect(0, 0, 1200, 720);
  if (frames.length) {
    if (now - lastReceive > 3000) {
      disconnect(
        "The server stopped sending state. Reconnect to resync.",
        true,
      );
      requestAnimationFrame(render);
      return;
    }
    const latest = frames.at(-1),
      target = latest.t + (now - lastReceive) / 1000 - 0.1;
    let before = frames[0],
      after = latest;
    for (const frame of frames) {
      if (frame.t <= target) before = frame;
      else {
        after = frame;
        break;
      }
    }
    const fraction =
      after.t === before.t ? 1 : (target - before.t) / (after.t - before.t);
    drawPaint(latest);
    ctx.drawImage(paintCanvas, 0, 0);
    const rows = interpolatePlayers(before, after, fraction);
    for (const row of rows) if (row[0] !== you) drawPlayer(row, now);
    const local = rows.find((row) => row[0] === you);
    if (local) drawPlayer(local, now);
  }
  requestAnimationFrame(render);
}
requestAnimationFrame(render);
