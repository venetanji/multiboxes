# Two-hour tutorial: a shared physics world

**Goal:** understand client → application messages, shared state and server-owned
state changes by modifying a working game. The networking and physics starter is
provided. No database, accounts or complete engine implementation is required.

Before class: teacher rehearses two devices on campus Wi-Fi, checks the chosen
HTTP or WSS endpoint and allowed browser origin, and keeps the teacher token
private. Students need Python 3.11/3.12, a browser and this checkout. If installation
fails, pair with someone whose supplied starter runs and inspect the same files.

| Minutes | Activity | Evidence to show your partner |
| --- | --- | --- |
| 0–15 | Install and run the supplied starter | Local client connects and shows your pink YOU square |
| 15–30 | Connect two tabs | Two identities, balanced BLACK/WHITE teams, shared painting |
| 30–50 | Inspect input/state messages | One input message and one complete state snapshot |
| 50–70 | Change one server rule | A visible difference affecting both clients |
| 70–85 | Observe server authority | A rejected forged state update and an unchanged shared rule |
| 85–100 | Blur, disconnect and reconnect | Released input, removed old square, full rejoin state |
| 100–110 | Join the classroom world | The same client connected to the teacher's server |
| 110–120 | Explain the message/state cycle | A short account of input → physics → paint → snapshot → render |

## 0–15: run the starter

Follow [README setup](README.md#run-locally). Start:

```sh
python -m multibox.game_server
```

Open http://localhost:8000, enter a nickname and click Connect. Move with arrows or
WASD. Jump once, release, land and jump again. Hold Down while falling. The server
paints your square's footprint only when its downward velocity exceeds the paint
threshold. There is no paint button or mass toggle.

## 15–30: two views, one world

Open a second tab. Confirm different temporary identities and balanced teams. The
pink outline and YOU label belong only to the square controlled by that tab.
Teammates can support one another: stack, jump from a square, and descend over a
new area. A side bump does not recharge jumping. Holding Up through a landing
does not automatically jump again; a fresh press is required.

Find a patch painted by the other team and repaint it while descending. Compare
both screens' scores. Grey is neutral and is included in percentage denominators.

## 30–50: inspect the messages

Open browser developer tools → Network → WS → `/ws` → Messages (names vary by
browser). Reconnect while recording. Find:

```json
{"type":"join","v":1,"nickname":"Box"}
{"type":"input","seq":12,"left":false,"right":true,"jump":false,"down":false}
```

The welcome includes `you` and a complete `state`. Following snapshots contain the
whole grid and roster. Find your row by matching `you` to its first value. Decode
it using [the row table](docs/protocol.md#state). `vy > 0` means descending because
screen y increases downward. Notice that input messages request buttons, not x/y,
team or score. Held input is refreshed at 20 Hz; physics steps independently.

Trace these files together:

1. `static/app.mjs`: `sendInput` sends held buttons.
2. `protocol.py`: `parse_input` checks types and permitted fields.
3. `simulation.py`: `World.step` applies force/impulse, steps Pymunk and paints.
4. `game_server.py`: `Hub.publish` serializes one full snapshot for all clients.
5. `static/app.mjs`: rendering interpolates positions between snapshots.

Distinguish an HTTP request/response (loading HTML or `/health`) from a continuing
bidirectional WebSocket connection. OSC is a format commonly carried by UDP;
WebSockets here use TCP. They are different transports, not different physics.

## 50–70: change a rule

Stop your **local** server. In `simulation.py`, change one `Config` default, such as
`jump_speed` from 390 to 460 or `down_acceleration` from 1400 to 900. Restart the
server and reconnect both tabs. Predict and observe the change. Keep forces small
enough for collisions to remain useful, and change one value at a time.

Run `python -m pytest tests/test_simulation.py -q`. Explain any failed expectation:
some tests intentionally pin the original game feel. Do not remove validation or
assertions simply to get green output. Restore your experiment before joining the
teacher's world if you want to keep the original local behavior.

An optional renderer exercise: change the local outline colour in `drawPlayer`.
Only that browser's display changes; the authoritative team and score do not.

## 70–85: observe authority

Use a separate developer-tools Console connection so the intentionally invalid
message does not interfere with your playing tab:

```js
const probe = new WebSocket(document.getElementById('server').value);
probe.onopen = () => probe.send(JSON.stringify({type:'join',v:1,nickname:'probe'}));
probe.onmessage = event => {
  const message = JSON.parse(event.data);
  if (message.type === 'welcome')
    probe.send(JSON.stringify({type:'input',seq:0,left:false,right:false,jump:false,down:false,x:999}));
};
probe.onclose = event => console.log(event.code, event.reason);
```

The server rejects the extra `x` field (code 1008) and cleans up that square. A
client cannot assign itself a team, give itself unlimited jumps, set a score or
reset everyone's round. Discuss why changing Canvas pixels cannot change shared
physics. The teacher's HTTP reset API uses a private bearer token, never a token
embedded in student JavaScript.

## 85–100: lifecycle and resynchronization

Hold a movement key, switch focus away, then return. Inputs clear; inertia can
still carry a physical body briefly. Click Disconnect. The other tab should lose
that square. Reconnect: the old body is gone, the new identity gets a complete
current grid/roster, and team assignment is balanced again. Nicknames are labels,
not accounts or proof of identity.

Edit Server URL. The previous connection closes immediately; connecting to the
new URL requires clicking Connect. Try an unavailable local port and read the
error. A client must not display a fake successful session. Restore the original
URL and reconnect. Explain why replacing a full snapshot is safe while silently
dropping an incremental paint event would lose information.

## 100–110: classroom shared world

Use the teacher-provided full server URL. For same-origin local HTTP, the supplied
client defaults to `ws://localhost:8000/ws`. A hosted HTTPS Pages client requires a
WSS endpoint with a valid certificate and an explicitly allowed origin. An IP
address alone does not provide TLS. If hosted-to-local access is blocked, return
to the HTTP client served by your local Python app; do not disable browser security.

The shared world runs on one Python process. Your local rule edits cannot change
it. Work as a team to build a stack, reach higher ground, descend and repaint.

## 110–120: explain and extend

Show your partner the input/state messages and describe one visible state change.
Separate transport (WebSocket/TCP), application logic (team, jump and painting),
physics (Pymunk) and rendering (Canvas/Pygame). Explain how a slow reader is bounded
and why localhost performance is not the same as campus Wi-Fi performance.

**Next week:** design a final-round results record with round ID, time, team
coverage and winner. Save it once when the application finishes a round, outside
the physics loop. Discuss how to retry without inserting the same result twice.
Do not add a database write for every physics tick or input packet today.
