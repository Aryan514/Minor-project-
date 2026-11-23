# equipment/console.py
# Operator console: a stdin thread for the human operator and a local TCP control socket
# (127.0.0.1:5100, one text command per line) so the harness can drive the very same functions.
# Every command goes through the core and therefore the arbiter, with origin OPERATOR.
# Serves N1 (the operator is just a third origin; no bypass path).
"""Operator console + control socket (CLAUDE.md section 9, decision D5)."""

from __future__ import annotations

import json
import logging
import socketserver
import sys
import threading
from typing import Callable, Optional

from equipment import config
from equipment.config import ControlState, Origin
from equipment.core import CommandResult, EquipmentCore

_log = logging.getLogger(__name__)

HELP = (
    "commands: remote | local | offline | lease ua | lease off | start | stop | limit <x> | status | quit"
)


class OperatorConsole:
    """Parses console commands and submits them to the core as OPERATOR."""

    def __init__(self, core: EquipmentCore, on_quit: Optional[Callable[[], None]] = None) -> None:
        """Create the console; `on_quit` is called when the `quit` command is received."""
        self._core = core
        self._on_quit = on_quit

    def execute(self, line: str) -> str:
        """Run one command line and return a one-line reply."""
        words = line.strip().lower().split()
        if not words:
            return ""
        cmd, args = words[0], words[1:]
        result: Optional[CommandResult] = None
        if cmd == "remote":
            result = self._core.set_control_state(Origin.OPERATOR, ControlState.ONLINE_REMOTE)
        elif cmd == "local":
            result = self._core.set_control_state(Origin.OPERATOR, ControlState.ONLINE_LOCAL)
        elif cmd == "offline":
            result = self._core.set_control_state(Origin.OPERATOR, ControlState.EQUIPMENT_OFFLINE)
        elif cmd == "lease" and args in (["ua"], ["off"]):
            result = self._core.set_lease(Origin.OPERATOR, args == ["ua"])
        elif cmd in ("start", "stop"):
            result = self._core.submit_command(Origin.OPERATOR, cmd.upper())
        elif cmd == "limit" and len(args) == 1:
            result = self._core.submit_ec_write(Origin.OPERATOR, config.ECID_TEMP_HIGH_LIMIT, args[0])
        elif cmd == "status":
            return json.dumps(self._core.snapshot())
        elif cmd == "quit":
            if self._on_quit is not None:
                self._on_quit()
            return "bye"
        elif cmd == "help":
            return HELP
        else:
            return f"unknown command {line.strip()!r}; {HELP}"
        if result.ok:
            return f"OK seq={result.seq}"
        return f"REJECTED seq={result.seq} code={result.gem_code} ua={result.ua_status} reason={result.reason}"

    # ------------------------------------------------------------------ stdin
    def start_stdin_thread(self) -> threading.Thread:
        """Read commands from stdin in a daemon thread (interactive use)."""

        def loop() -> None:
            print(HELP, flush=True)
            for line in sys.stdin:
                try:
                    reply = self.execute(line)
                except Exception as exc:  # noqa: BLE001
                    reply = f"ERROR {exc}"
                if reply:
                    print(reply, flush=True)
                if line.strip().lower() == "quit":
                    return

        t = threading.Thread(target=loop, name="console-stdin", daemon=True)
        t.start()
        return t


class _ControlHandler(socketserver.StreamRequestHandler):
    """One connection: read lines, reply one line per command."""

    def handle(self) -> None:
        console: OperatorConsole = self.server.console  # type: ignore[attr-defined]
        for raw in self.rfile:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                reply = console.execute(line)
            except Exception as exc:  # noqa: BLE001
                reply = f"ERROR {exc}"
            self.wfile.write((reply + "\n").encode("utf-8"))
            self.wfile.flush()


class ControlSocketServer(socketserver.ThreadingTCPServer):
    """Local-only control socket for the harness."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, console: OperatorConsole, host: str = config.CONTROL_HOST, port: int = config.CONTROL_PORT):
        """Bind to host:port (127.0.0.1 only)."""
        super().__init__((host, port), _ControlHandler)
        self.console = console

    def start_thread(self) -> threading.Thread:
        """Serve in a daemon thread."""
        t = threading.Thread(target=self.serve_forever, name="control-socket", daemon=True)
        t.start()
        return t


def send_control_command(line: str, host: str = config.CONTROL_HOST, port: int = config.CONTROL_PORT,
                         timeout: float = 5.0) -> str:
    """Client helper used by the harness/demo: send one console command, return the reply line."""
    import socket

    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall((line.strip() + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    return data.decode("utf-8").strip()


if __name__ == "__main__":  # python -m equipment.console "remote"
    print(send_control_command(" ".join(sys.argv[1:]) or "status"))
