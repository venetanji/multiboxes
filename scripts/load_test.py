#!/usr/bin/env python3
"""Bounded active-game load test of a NEW LOCAL server, never a remote endpoint.

pip install -e '.[test]'
python scripts/load_test.py --clients 100 --seconds 120 --slow 5 --output /tmp/load-100.json
Run without concurrent browser/tests for useful numbers. Payload bandwidth excludes
TCP/TLS/Wi-Fi framing. This is loopback capacity evidence, not a campus rehearsal.
"""

import argparse
import asyncio
from collections import deque
import json
import math
import os
from pathlib import Path
import platform
import secrets
import socket
import subprocess
import sys
import time

import httpx
import psutil
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from multibox.game_server import distribution
from multibox.wire import Decoder


class Bot:
    def __init__(self, index, url, *, slow=False, input_hz=20):
        self.index, self.url, self.slow, self.input_hz = index, url, slow, input_hz
        self.inputs_sent = self.input_bytes = 0
        self.ws = None
        self.ready = asyncio.Event()
        self.controlled_close = False
        self.connections = self.errors = self.slow_closes = 0
        self.bytes = self.states = self.paint_changes = 0
        self.moved = False
        self.latencies = deque(maxlen=2000)
        self.join_ms = None

    async def run(self):
        first_attempt = time.perf_counter()
        while True:
            try:
                async with connect(
                    self.url,
                    max_size=131072,
                    max_queue=1,
                    compression=None,
                    close_timeout=1,
                    open_timeout=10,
                    proxy=None,
                ) as ws:
                    self.ws = ws
                    if self.slow:
                        ws.transport.get_extra_info("socket").setsockopt(
                            socket.SOL_SOCKET, socket.SO_RCVBUF, 4096
                        )
                    await ws.send(json.dumps({"type": "join", "v": 2, "nickname": f"bot {self.index}"}))
                    welcome_raw = await ws.recv()
                    self.bytes += len(welcome_raw)
                    welcome = json.loads(welcome_raw)
                    if welcome.get("type") != "welcome":
                        raise ValueError("missing welcome")
                    self.connections += 1
                    self.ready.set()
                    if self.join_ms is None:
                        self.join_ms = (time.perf_counter() - first_attempt) * 1000
                    you, decoder, latest_tick = welcome["you"], Decoder(), -1
                    pending, seq, last_ack, previous_paint = {}, 0, -1, None
                    origin = None
                    jump_ready = False

                    async def send():
                        nonlocal seq
                        next_send = time.perf_counter()
                        while True:
                            elapsed = time.perf_counter() - first_attempt
                            right = int(elapsed / 2.5 + self.index) % 2 == 0
                            buttons = {
                                "left": not right,
                                "right": right,
                                "jump": jump_ready and (seq + self.index) % 3 == 0,
                                "down": int(elapsed * 0.7 + self.index) % 4 == 0,
                            }
                            pending[seq] = time.perf_counter()
                            # Bound test instrumentation even when a slow reader never acknowledges.
                            if len(pending) > 100:
                                del pending[min(pending)]
                            raw_input = json.dumps({"type": "input", "seq": seq, **buttons})
                            await ws.send(raw_input)
                            self.inputs_sent += 1
                            self.input_bytes += len(raw_input)
                            seq += 1
                            if self.input_hz == 20:
                                # Match browser setInterval's deadline cadence, not work + sleep drift.
                                next_send += 0.05
                                now = time.perf_counter()
                                if now - next_send > 0.1:
                                    next_send = now
                                await asyncio.sleep(max(0, next_send - now))
                            else:
                                await asyncio.sleep(0.1)  # Preserve the original 10Hz comparison workload.

                    async def receive():
                        nonlocal latest_tick, last_ack, previous_paint, origin, jump_ready
                        while True:
                            if self.slow:
                                await asyncio.sleep(2)
                            raw = await ws.recv()
                            self.bytes += len(raw)
                            if isinstance(raw, str):
                                decoder.metadata(json.loads(raw))
                                continue
                            state = decoder.frame(raw)
                            if state is None:
                                continue
                            if state["tick"] < latest_tick:
                                raise ValueError("out-of-order state")
                            latest_tick = state["tick"]
                            self.states += 1
                            row = next((p for p in state["players"] if p[0] == you), None)
                            if row is None:
                                raise ValueError("own identity missing")
                            jump_ready = row[7]
                            if origin is None:
                                origin = row[3:5]
                            if math.dist(origin, row[3:5]) > 5:
                                self.moved = True
                            if previous_paint is not None and previous_paint != state["paint"]:
                                self.paint_changes += 1
                            previous_paint = state["paint"]
                            ack = row[8]
                            if ack > last_ack:
                                if ack in pending and not self.slow:
                                    self.latencies.append((time.perf_counter() - pending[ack]) * 1000)
                                for old in list(pending):
                                    if old <= ack:
                                        del pending[old]
                                last_ack = ack

                    tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
                    try:
                        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for task in done:
                            task.result()
                    finally:
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
            except (ConnectionClosed, OSError, TimeoutError):
                if self.slow:
                    self.slow_closes += 1
                elif not self.controlled_close:
                    self.errors += 1
            finally:
                self.controlled_close = False
                self.ws = None
            await asyncio.sleep(0.1)

    async def reconnect(self):
        if self.ws:
            self.controlled_close = True
            await self.ws.close(code=1000, reason="load-test reconnect")


def read_optional(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return "unavailable"


def environment(input_hz):
    model = next(
        (
            line.split(":", 1)[1].strip()
            for line in read_optional("/proc/cpuinfo").splitlines()
            if line.startswith("model name")
        ),
        platform.machine(),
    )
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_model": model,
        "logical_cpus": os.cpu_count(),
        "cpu_quota": read_optional("/sys/fs/cgroup/cpu.max"),
        "memory_limit": read_optional("/sys/fs/cgroup/memory.max"),
        "transport": "loopback WebSocket v2, no TLS/compression",
        "generator": f"same machine, separate process from server; {input_hz} Hz held input plus fresh jump presses",
    }


async def exercise(args, process, port, token):
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{port}", trust_env=False, headers={"authorization": f"Bearer {token}"}
    ) as http:
        for _ in range(100):
            try:
                if (await http.get("/health")).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if process.poll() is not None:
                raise RuntimeError("local test server exited; inspect adjacent server log")
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("local server not ready")
        bots = [
            Bot(i, f"ws://127.0.0.1:{port}/ws", slow=i < args.slow, input_hz=args.input_hz)
            for i in range(args.clients)
        ]
        tasks = [asyncio.create_task(bot.run()) for bot in bots]
        try:
            await asyncio.wait_for(asyncio.gather(*(bot.ready.wait() for bot in bots)), timeout=20)
            print(f"{args.clients} simultaneous joins complete; 5s warmup", flush=True)
            await asyncio.sleep(5)
            baseline = (await http.get("/admin/metrics")).json()
            for bot in bots:
                bot.latencies.clear()
                bot.bytes = bot.states = bot.inputs_sent = bot.input_bytes = 0
            server = psutil.Process(process.pid)
            generator = psutil.Process()
            server.cpu_percent()
            generator.cpu_percent()
            samples, churned = [], set()
            start = time.perf_counter()
            next_progress = 20
            while time.perf_counter() - start < args.seconds:
                await asyncio.sleep(1)
                elapsed = time.perf_counter() - start
                samples.append(
                    {
                        "t": round(elapsed, 2),
                        "rss_mb": round(server.memory_info().rss / 2**20, 2),
                        "cpu_percent": server.cpu_percent(),
                        "generator_cpu_percent": generator.cpu_percent(),
                    }
                )
                for fraction in (0.35, 0.7):
                    if elapsed >= args.seconds * fraction and fraction not in churned:
                        churned.add(fraction)
                        fast = [bot for bot in bots if not bot.slow]
                        await asyncio.gather(*(bot.reconnect() for bot in fast[: max(1, len(fast) // 10)]))
                if elapsed >= next_progress:
                    print(
                        f"{args.clients} clients: {elapsed:.0f}s, RSS {samples[-1]['rss_mb']} MiB, CPU {samples[-1]['cpu_percent']}%",
                        flush=True,
                    )
                    next_progress += 20
                for task in tasks:
                    if task.done():
                        task.result()
                        raise RuntimeError("load bot stopped unexpectedly")
            duration = time.perf_counter() - start
            final = (await http.get("/admin/metrics")).json()
            fast = [bot for bot in bots if not bot.slow]
            rates = [bot.states / duration for bot in fast]
            latencies = [sample for bot in fast for sample in bot.latencies]
            tick_hz = (final["tick"] - baseline["tick"]) / duration
            result = {
                "environment": environment(args.input_hz),
                "protocol": 2,
                "input_hz_target": args.input_hz,
                "input_hz_observed": distribution([bot.inputs_sent / duration for bot in fast]),
                "input_payload_mbit_s": round(sum(bot.input_bytes for bot in bots) * 8 / duration / 1e6, 3),
                "clients": args.clients,
                "slow_readers": args.slow,
                "duration_seconds": round(duration, 2),
                "warmup_seconds": 5,
                "server_metrics": final,
                "tick_hz": round(tick_hz, 3),
                "fast_client_snapshot_hz": distribution(rates),
                "input_to_snapshot_ms": distribution(latencies),
                "latency_samples": len(latencies),
                "join_ms": distribution([bot.join_ms for bot in bots]),
                "normal_unexpected_disconnects": sum(bot.errors for bot in fast),
                "slow_reader_disconnects": sum(bot.slow_closes for bot in bots),
                "connections_including_rejoins": sum(bot.connections for bot in bots),
                "moved_clients": sum(bot.moved for bot in bots),
                "paint_snapshot_changes": sum(bot.paint_changes for bot in fast),
                "server_payload_mbit_s": round(
                    (final["sent_bytes"] - baseline["sent_bytes"]) * 8 / duration / 1e6, 3
                ),
                "consumed_payload_mbit_s": round(sum(bot.bytes for bot in bots) * 8 / duration / 1e6, 3),
                "server_cpu_percent": distribution([s["cpu_percent"] for s in samples]),
                "generator_cpu_percent": distribution([s["generator_cpu_percent"] for s in samples]),
                "rss_mb": {
                    "start": samples[0]["rss_mb"],
                    "end": samples[-1]["rss_mb"],
                    "peak": max(s["rss_mb"] for s in samples),
                },
                "samples": samples,
            }
            result["checks"] = {
                "all_clients_moved": result["moved_clients"] == args.clients,
                "painting_active": final["paint_writes"] > baseline["paint_writes"],
                "jumping_active": final["jumps"] > baseline["jumps"],
                "normal_connections_stable": result["normal_unexpected_disconnects"] == 0,
                "tick_hz_at_least_59": tick_hz >= 59,
                "snapshot_p50_at_least_19": result["fast_client_snapshot_hz"]["p50"] >= 19,
                "input_p95_under_150ms": result["input_to_snapshot_ms"]["p95"] < 150,
                "queue_at_most_one": final["queue_max"] <= 1,
            }
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(1)
        result["after_disconnect"] = (await http.get("/admin/metrics")).json()
        result["checks"]["all_bodies_cleaned"] = result["after_disconnect"]["players"] == 0
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-hz", type=int, choices=(10, 20), default=20)
    parser.add_argument("--clients", type=int, default=100)
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument("--slow", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 2 <= args.clients <= 150 or not 5 <= args.seconds <= 300 or not 0 <= args.slow < args.clients:
        parser.error("clients 2..150, seconds 5..300, slow 0..clients-1 required")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    token = secrets.token_urlsafe(32)
    env = os.environ.copy() | {"MULTIBOX_TEACHER_TOKEN": token}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_suffix(".server.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "multibox.game_server", "--port", str(port)],
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            result = asyncio.run(exercise(args, process, port, token))
            args.output.write_text(json.dumps(result, indent=2) + "\n")
            print(
                json.dumps(
                    {
                        key: value
                        for key, value in result.items()
                        if key not in ("samples", "after_disconnect")
                    },
                    indent=2,
                )
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    if not all(result["checks"].values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
