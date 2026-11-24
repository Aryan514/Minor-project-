# harness/control_panel.py
# Back-end of the dashboard's control features: start/stop the whole system exactly as harness.demo does, and
# send commands ONLY through the entry points any external user has: the GEM host's command port (real S2F41/S2F15
# on HSMS), the ua_client one-shot process (real OPC UA Call), and the equipment console's control socket. Nothing
# here touches the core directly, so every command still passes the arbiter. Also: policy table straight from
# arbiter.decide, a real OPC UA browse, the race demo, and an optional tshark packet counter.
# Serves N1 (arbiter exercised live), N2 (model browser) and N3 (panel-driven runs are judged by the checker).
"""Control panel back-end for harness.web_view (live mode, 127.0.0.1 only)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import threading
import time
from typing import Any, Optional

from clients.ua_client import browse_tree
from equipment import arbiter, config
from equipment.config import Action, ControlState, Origin
from equipment.console import send_control_command
from harness import checker, race_demo
from harness.scenarios import PY, GemRelay, Run, busy_ports, race

TSHARK_CANDIDATES = (r"D:\Wireshark\tshark.exe", r"C:\Program Files\Wireshark\tshark.exe", "/usr/bin/tshark")

# name -> (label, how it is sent)
COMMANDS: dict[str, str] = {
    "gem_start": "GEM host: S2F41 START (via the GEM host's command port)",
    "gem_stop": "GEM host: S2F41 STOP",
    "gem_limit": "GEM host: S2F15 ECID 201",
    "ua_start": "UA client: Call Start() (ua_client one-shot)",
    "ua_stop": "UA client: Call Stop()",
    "ua_limit": "UA client: Call SetTempHighLimit(value)",
    "both_start": "GEM S2F41 START + UA Call Start released by one barrier (like S3)",
    "remote": "Operator console: remote", "local": "Operator console: local", "offline": "Operator console: offline",
    "lease_ua": "Operator console: lease ua", "lease_off": "Operator console: lease off",
    "kill_gem": "Kill the GEM host process (simulated crash)", "reconnect_gem": "Start the GEM host again",
}


def find_tshark() -> Optional[str]:
    """tshark on PATH or in a usual install folder; None if not installed."""
    found = shutil.which("tshark")
    if found:
        return found
    return next((p for p in TSHARK_CANDIDATES if os.path.exists(p)), None)


class PacketCounter:
    """Optional background tshark on the loopback adapter: packets per port (5000 / 4840). Passive capture only."""

    def __init__(self, tshark: str) -> None:
        self.tshark = tshark
        self.counts = {config.HSMS_PORT: 0, 4840: 0}
        self.proc: Optional[subprocess.Popen] = None
        self.error = ""

    def start(self) -> None:
        """Start capturing; count lines of `srcport dstport`."""
        iface = r"\Device\NPF_Loopback" if os.name == "nt" else "lo"
        cmd = [self.tshark, "-i", iface, "-f", f"tcp port {config.HSMS_PORT} or tcp port 4840", "-l", "-T", "fields",
               "-e", "tcp.srcport", "-e", "tcp.dstport"]
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0  # type: ignore[attr-defined]
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                         creationflags=flags)
        except OSError as exc:
            self.error = str(exc)
            return
        threading.Thread(target=self._read, name="tshark-counter", daemon=True).start()

    def _read(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for line in self.proc.stdout:
            parts = line.split()
            for port in self.counts:
                if str(port) in parts:
                    self.counts[port] += 1

    def stop(self) -> None:
        """Stop tshark (tree kill)."""
        if self.proc is not None and self.proc.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True)
            else:
                self.proc.terminate()


def policy_table() -> list[dict[str, Any]]:
    """The arbitration table computed from arbiter.decide itself (not copied from the docs)."""
    rows = []
    for state, lease, label in ((ControlState.ONLINE_REMOTE, False, "ONLINE_REMOTE"),
                                (ControlState.ONLINE_LOCAL, False, "ONLINE_LOCAL"),
                                (ControlState.EQUIPMENT_OFFLINE, False, "EQUIPMENT_OFFLINE"),
                                (ControlState.EQUIPMENT_OFFLINE, True, "EQUIPMENT_OFFLINE + lease")):
        cells = {}
        for origin in (Origin.GEM_HOST, Origin.UA_CLIENT, Origin.OPERATOR):
            ds = {a.value: arbiter.decide(state, lease, origin, a) for a in (Action.START, Action.STOP, Action.EC_WRITE)}
            allowed = [a for a, d in ds.items() if d.allowed]
            if len(allowed) == 3:
                cells[origin.value] = {"text": "allowed", "kind": "ok"}
            elif not allowed:
                cells[origin.value] = {"text": f"rejected: {next(iter(ds.values())).reason}", "kind": "no"}
            else:
                cells[origin.value] = {"text": " / ".join(allowed) + " only", "kind": "part"}
        rows.append({"state": label, "control_state": state.name, "lease": lease,
                     "authority": arbiter.authority_holder(state, lease).value, "cells": cells})
    return rows


class ControlPanel:
    """Starts/stops the system and runs panel commands. One action at a time."""

    def __init__(self, enabled: bool, on_run_started: Any = None) -> None:
        self.enabled = enabled
        self.run: Optional[Run] = None
        self.state = "stopped"  # stopped | starting | running | stopping
        self.message = "system stopped"
        self.verdict: Optional[dict[str, Any]] = None
        self.last_result: Optional[dict[str, Any]] = None
        self.tshark = find_tshark()
        self.counter: Optional[PacketCounter] = None
        self._lock = threading.Lock()  # serialises commands
        self._on_run_started = on_run_started

    # ---- status
    def status(self) -> dict[str, Any]:
        """For GET /api/system."""
        return {"enabled": self.enabled, "state": self.state, "message": self.message,
                "run_id": self.run.run_id if self.run else None, "verdict": self.verdict,
                "last_result": self.last_result, "tshark": bool(self.tshark),
                "packets": dict(self.counter.counts) if self.counter and self.state == "running" else None,
                "commands": COMMANDS}

    # ---- system
    def start_system(self) -> dict[str, Any]:
        """Launch equipment + both listening clients in the background (like harness.demo)."""
        if not self.enabled:
            return {"ok": False, "error": "control is disabled (only available in live mode on 127.0.0.1)"}
        if self.state != "stopped":
            return {"ok": False, "error": f"system is {self.state}"}
        busy = busy_ports()  # safe: our equipment is not running yet
        if busy:
            return {"ok": False, "error": f"ports {busy} are in use (another equipment or client is running)"}
        self.state, self.message, self.verdict = "starting", "starting equipment, GEM host, OPC UA client…", None
        threading.Thread(target=self._start, name="panel-start", daemon=True).start()
        return {"ok": True}

    def _start(self) -> None:
        run = Run("PANEL", "Run driven from the web dashboard's control panel")
        self.run = run
        try:
            if self.tshark:
                self.counter = PacketCounter(self.tshark)
                self.counter.start()
            if self._on_run_started:
                self._on_run_started(run.dir)
            run.start()
            self.state, self.message = "running", f"running: {run.run_id}"
        except Exception as exc:  # noqa: BLE001
            self.message = f"start failed: {exc}"
            run.meta.setdefault("t_end_ns", time.time_ns())
            run.stop()
            if self.counter:
                self.counter.stop()
            self.state = "stopped"

    def stop_system(self) -> dict[str, Any]:
        """End the evaluation window, stop everything, run the checker on the run."""
        if self.state != "running" or self.run is None:
            return {"ok": False, "error": f"system is {self.state}"}
        self.state, self.message = "stopping", "stopping and checking…"
        threading.Thread(target=self._stop, name="panel-stop", daemon=True).start()
        return {"ok": True}

    def _stop(self) -> None:
        run = self.run
        assert run is not None
        with self._lock:
            try:
                run.end_window(settle_s=2.0)
            finally:
                run.stop()
                if self.counter:
                    self.counter.stop()
        data = checker.RunData.load(run.dir)
        results = checker.check_run(data)
        md = checker.write_reports(data, results, run.dir / "report")
        self.verdict = {"overall": checker.overall(results), "report": str(md),
                        "rows": [[r.invariant, r.side, r.status, r.detail] for r in results],
                        "ports_free": not busy_ports()}
        self.state, self.message = "stopped", f"stopped {run.run_id}: checker {self.verdict['overall']}"

    def shutdown(self) -> None:
        """Called when the dashboard exits: never leave the system running."""
        if self.state == "running":
            self._stop()

    # ---- commands
    def command(self, name: str, value: Optional[float] = None) -> dict[str, Any]:
        """Run one panel command and return its real reply (code + reason)."""
        if not self.enabled:
            return {"ok": False, "error": "control is disabled"}
        if name not in COMMANDS:
            return {"ok": False, "error": f"unknown command {name}"}
        if self.state != "running" or self.run is None:
            return {"ok": False, "error": "start the system first"}
        with self._lock:
            t0 = time.perf_counter()
            before = self._status()
            try:
                result = self._do(name, value)
            except Exception as exc:  # noqa: BLE001 - show the failure on the panel
                result = {"reply": f"error: {exc}", "accepted": False}
            after = self._status()
            rej = (after or {}).get("last_rejection")
            if rej and before is not None and rej["seq"] > before.get("last_seq", 0):
                result.setdefault("reason", rej["reason"])
                result.setdefault("rejected_by_core", f"{rej['origin']} {rej['what']} (seq {rej['seq']})")
            result.update({"command": name, "label": COMMANDS[name], "value": value,
                           "ms": round((time.perf_counter() - t0) * 1000), "ts_ns": time.time_ns()})
            self.last_result = result
            return result

    def _status(self) -> Optional[dict[str, Any]]:
        try:
            return json.loads(send_control_command("status", timeout=3))
        except (OSError, ValueError):
            return None

    def _ua_one_shot(self, args: list[str]) -> str:
        assert self.run is not None
        out = subprocess.run([PY, "-m", "clients.ua_client", *args, "--run-id", self.run.run_id],
                             capture_output=True, text=True, timeout=60)
        lines = out.stdout.strip().splitlines()
        return lines[-1] if lines else (out.stderr.strip().splitlines() or ["no output"])[-1]

    def _do(self, name: str, value: Optional[float]) -> dict[str, Any]:
        run = self.run
        assert run is not None
        if name in ("gem_start", "gem_stop", "gem_limit"):
            action = {"gem_start": "start", "gem_stop": "stop", "gem_limit": "set-limit"}[name]
            r = GemRelay.call(action, value)
            if "error" in r:
                return {"reply": f"GEM host error: {r['error']}", "accepted": False}
            return {"reply": f"{r['code_name']} {r['code']}", "accepted": r["code"] == 0}
        if name in ("ua_start", "ua_stop", "ua_limit"):
            args = {"ua_start": ["--start"], "ua_stop": ["--stop"], "ua_limit": ["--set-limit", str(value)]}[name]
            status = self._ua_one_shot(args)
            return {"reply": f"StatusCode {status}", "accepted": status == "Good"}
        if name == "both_start":
            assert run.ua is not None
            snap = json.loads(send_control_command("status"))
            holder = arbiter.authority_holder(ControlState[snap["control_state"]], snap["lease_ua"]).value
            # A conflict round for I5 needs a contender that may win: IDLE and authority held by GEM_HOST or
            # UA_CLIENT. Otherwise the policy rejects both (e.g. LOCAL) and the press is shown but not counted.
            conflict = snap["processing_state"] == "IDLE" and holder in ("GEM_HOST", "UA_CLIENT")
            gem, ua_status, t0, t1 = race("start", None, "Start", (), run.ua)
            if conflict:
                run.meta["rounds"].append({"i": len(run.meta["rounds"]) + 1, "action": "START",
                                           "seq_before": snap["last_seq"], "t0_ns": t0, "t1_ns": t1,
                                           "gem_code": gem.get("code"), "ua_status": ua_status,
                                           "expected_winner": holder})
            winners = [s for s, ok in (("GEM", gem.get("code") == 0), ("UA", ua_status == "Good")) if ok]
            note = f"conflict round (authority {holder}) - judged by I5" if conflict else                 f"not a conflict round (authority {holder}, {snap['processing_state']}) - not counted for I5"
            return {"reply": f"GEM HCACK {gem.get('code')}  |  UA {ua_status}   [{note}]",
                    "accepted": len(winners) == 1, "winners": winners}
        if name in ("remote", "local", "offline", "lease_ua", "lease_off"):
            line = {"lease_ua": "lease ua", "lease_off": "lease off"}.get(name, name)
            reply = send_control_command(line)
            return {"reply": reply, "accepted": reply.startswith("OK")}
        if name == "kill_gem":
            run.kill_gem()
            return {"reply": "GEM host process killed (HSMS link will drop)", "accepted": True}
        if name == "reconnect_gem":
            if run.gem is not None and run.gem.poll() is None:
                return {"reply": "GEM host is already running", "accepted": False}
            run.start_gem()
            return {"reply": "GEM host connected, reports defined again", "accepted": True}
        raise ValueError(name)

    # ---- read-only helpers
    @staticmethod
    def browse(run_id: Optional[str]) -> dict[str, Any]:
        """A real OPC UA browse of opc.tcp://127.0.0.1:4840 by a short-lived asyncua client."""
        try:
            return {"ok": True, "tree": asyncio.run(asyncio.wait_for(browse_tree(config.OPCUA_CLIENT_ENDPOINT,
                                                                                 run_id), 30))}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"browse failed ({exc!r}); is the system running?"}

    @staticmethod
    def race_demo(n: int = 200) -> dict[str, Any]:
        """Unsafe vs real core, in-process (does not touch the running system)."""
        return race_demo.run_both(n)

