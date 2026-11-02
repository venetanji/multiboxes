#!/usr/bin/env python3
"""Convenience launcher; module entry points accept all server/client options."""

import subprocess
import sys


def main():
    commands = {
        "server": ["-m", "multibox.game_server"],
        "client": ["-m", "multibox.game_client"],
        "test": ["-m", "pytest"],
    }
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print("Usage: python launcher.py server|client|test [options]")
        print("Local browser: http://localhost:8000 after starting server")
        return 2
    try:
        return subprocess.call([sys.executable, *commands[sys.argv[1]], *sys.argv[2:]])
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
