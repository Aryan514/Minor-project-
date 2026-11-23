# harness/scenarios.py
# Scenario runner S1..S6 (CLAUDE.md section 12): for each scenario a fresh run_id, the equipment with the sim
# sensor and a fixed seed, both listening clients, the scripted actions, a clean shutdown (no leftover process
# or port), then the checker -> results/<scenario>_summary.md + CSV.
# Concurrent commands use a threading.Barrier: GEM through the listener's HSMS session, UA through a
# persistent OPC UA session, released at the same instant.
# Serves N3 (normal, conflict and fault scenarios) and N1 (S3/S4 evidence for the arbiter).
"""python -m harness.scenarios S1|S2|S3|S4|S5|S6|all"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from asyncua import Client, ua

from clients.gem_host import RELAY_HOST, RELAY_PORT
from clients.ua_client import _status_name
from equipment import config
from equipment.console import send_control_command
from harness import checker

PORTS = (config.HSMS_PORT, 4840, config.CONTROL_PORT, RELAY_PORT)
PY = sys.executable
ORDER = ("S3", "S2", "S5", "S1", "S4", "S6")  # CLAUDE.md priority order


# ---------------------------------------------------------------------- process helpers
def busy_ports(ports: tuple[int, ...] = PORTS) -> list[int]:
    """Ports of this testbed that something is listening on.

    This probes by CONNECTING. Use it only when the equipment is not running (before start / after stop) or on
    ports where a probe is harmless (relay, OPC UA). Never probe the HSMS port of a running equipment: it accepts
    ONE session, and a probe that connects and closes at once can take that session (and with an abrupt close
    secsgem may stop listening). See docs/progress.md, "Wireshark capture", problem 1.
    """
    busy = []
    for port in ports:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                busy.append(port)
    return busy


def kill_tree(proc: Optional[subprocess.Popen]) -> None:
    """Hard-kill a process AND its children (on Windows the venv python.exe is a launcher with a child)."""
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        pass


def wait_for(pred: Callable[[], bool], timeout: float, step: float = 0.1, what: str = "condition") -> float:
    """Poll until pred() is true; return the seconds waited."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            if pred():
                return time.monotonic() - t0
        except (OSError, ValueError):
            pass
        time.sleep(step)
    raise TimeoutError(f"timed out after {timeout:.0f} s waiting for {what}")


def log_has(path: Path, kind: str, after_ns: int = 0) -> bool:
    """True if a JSONL log contains a record of `kind` written after `after_ns`."""
    return any(r.get("kind") == kind and r.get("ts_ns", 0) >= after_ns for r in checker.load_jsonl(path))


# ---------------------------------------------------------------------- protocol helpers
class GemRelay:
    """Sends host actions through the listening GEM host's HSMS session (decision D15)."""

    @staticmethod
    def open() -> socket.socket:
        """Pre-open a relay connection (so a barrier releases only the send)."""
        sock = socket.create_connection((RELAY_HOST, RELAY_PORT), timeout=5)
        sock.settimeout(30)
        return sock

    @staticmethod
    def send(sock: socket.socket, action: str, value: Optional[float] = None, **extra: Any) -> dict[str, Any]:
        """Send one action on an open connection and return the reply."""
        sock.sendall((json.dumps({"action": action, "value": value, "extra": extra}) + "\n").encode("utf-8"))
        with sock.makefile("r", encoding="utf-8") as f:
            return json.loads(f.readline())

    @classmethod
    def call(cls, action: str, value: Optional[float] = None, **extra: Any) -> dict[str, Any]:
        """Open, send, close."""
        with cls.open() as sock:
            return cls.send(sock, action, value, **extra)


class UaSession:
    """A persistent OPC UA session on its own event-loop thread, callable from plain threads."""

    def __init__(self, url: str = config.OPCUA_CLIENT_ENDPOINT) -> None:
        self._url = url
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="ua-session", daemon=True)
        self._thread.start()
        self.client: Optional[Client] = None
        self.idx = 0

    def _run(self, coro: Any, timeout: float = 30) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def connect(self) -> None:
        """Connect and resolve the namespace index."""
        async def go() -> None:
            self.client = Client(self._url)
            await self.client.connect()
            self.idx = await self.client.get_namespace_index(config.OPCUA_NAMESPACE_URI)
        self._run(go())

    def node(self, path: str) -> Any:
        """Node under Chamber1Tool by dotted path ('' = the tool)."""
        assert self.client is not None
        return self.client.get_node(ua.NodeId(config.TOOL_NAME + (f".{path}" if path else ""), self.idx))

    def call(self, method: str, *args: Any) -> str:
        """Call a Chamber1Tool method; return the StatusCode name."""
        async def go() -> str:
            try:
                await self.node("").call_method(f"{self.idx}:{method}", *args)
                return "Good"
            except ua.UaStatusCodeError as exc:
                return _status_name(exc.code)
        return self._run(go())

    def read(self, path: str) -> Any:
        """Read a variable value."""
        async def go() -> Any:
            return await self.node(path).read_value()
        return self._run(go())

    def run(self, coro_fn: Callable[["UaSession"], Any]) -> Any:
        """Run an arbitrary coroutine function (receives this session) on the session loop."""
        return self._run(coro_fn(self))

    def close(self) -> None:
        """Disconnect and stop the loop."""
        try:
            if self.client is not None:
                self._run(self.client.disconnect(), timeout=10)
        except Exception:  # noqa: BLE001
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)


def race(gem_action: str, gem_value: Optional[float], ua_method: str, ua_args: tuple,
         ua: UaSession) -> tuple[dict[str, Any], str, int, int]:
    """Fire a GEM host action and a UA method call at the same instant (barrier)."""
    barrier = threading.Barrier(2)
    out: dict[str, Any] = {}
    sock = GemRelay.open()

    def gem() -> None:
        barrier.wait()
        out["gem"] = GemRelay.send(sock, gem_action, gem_value)

    def uac() -> None:
        barrier.wait()
        out["ua"] = ua.call(ua_method, *ua_args)

    t0 = time.time_ns()
    threads = [threading.Thread(target=gem), threading.Thread(target=uac)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    t1 = time.time_ns()
    sock.close()
    return out["gem"], out["ua"], t0, t1


# ---------------------------------------------------------------------- run context
class Run:
    """Starts equipment + both listening clients, records scenario metadata, shuts everything down."""

    def __init__(self, scenario: str, description: str, seed: int = config.SIM_DEFAULT_SEED) -> None:
        self.scenario = scenario
        self.run_id = f"{scenario}_{time.strftime('%Y%m%d-%H%M%S')}"
        self.dir = Path.cwd() / config.RUNS_DIR / self.run_id
        self.meta: dict[str, Any] = {"scenario": scenario, "description": description, "seed": seed,
                                     "run_id": self.run_id, "rounds": [], "checks": [], "findings": [],
                                     "phases": []}
        self.seed = seed
        self.eq: Optional[subprocess.Popen] = None
        self.gem: Optional[subprocess.Popen] = None
        self.uac: Optional[subprocess.Popen] = None
        self.ua: Optional[UaSession] = None

    # ---- lifecycle
    def start(self) -> "Run":
        """Bring everything up and open the evaluation window."""
        busy = busy_ports()
        if busy:
            raise RuntimeError(f"ports {busy} are in use: stop the running equipment/clients first")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.eq = subprocess.Popen([PY, "-m", "equipment.main", "--no-console", "--run-id", self.run_id,
                                    "--seed", str(self.seed)],
                                   stdout=open(self.dir / "equipment.out", "w"), stderr=subprocess.STDOUT)
        wait_for(self._control_up, 30, what="equipment control port")
        # equipment.main prints READY only after both doors are started; reading it touches no port (the HSMS
        # port must not be probed, see busy_ports()).
        wait_for(lambda: "READY run_id=" in (self.dir / "equipment.out").read_text(encoding="utf-8", errors="replace"),
                 30, what="both doors (equipment READY)")
        self.start_gem()
        self.start_ua_listener()
        self.ua = UaSession()
        self.ua.connect()
        time.sleep(1.0)
        self.meta["t_start_ns"] = time.time_ns()
        self.phase("window open (both clients listening)")
        return self

    def _control_up(self) -> bool:
        try:
            return send_control_command("status", timeout=1).startswith("{")
        except OSError:
            return False

    def start_gem(self) -> None:
        """(Re)start the listening GEM host and wait until its reports are active."""
        t = time.time_ns()
        self.gem = subprocess.Popen([PY, "-m", "clients.gem_host", "--listen", "--quiet", "--run-id", self.run_id],
                                    stdout=open(self.dir / "gem_host.out", "a"), stderr=subprocess.STDOUT)
        wait_for(lambda: log_has(self.dir / config.GEM_HOST_LOG_FILE, "status", t), 60, what="GEM host listening")
        wait_for(lambda: RELAY_PORT in busy_ports((RELAY_PORT,)), 10, what="GEM relay port")

    def kill_gem(self) -> None:
        """Hard-kill the GEM host process (simulates a host crash / cable pull)."""
        kill_tree(self.gem)
        self.gem = None

    def start_ua_listener(self) -> None:
        """Start the listening UA client and wait until its subscriptions are active."""
        t = time.time_ns()
        self.uac = subprocess.Popen([PY, "-m", "clients.ua_client", "--listen", "--quiet", "--run-id", self.run_id],
                                    stdout=open(self.dir / "ua_client.out", "a"), stderr=subprocess.STDOUT)
        wait_for(lambda: log_has(self.dir / config.UA_CLIENT_LOG_FILE, "listening", t), 60, what="UA client listening")

    def phase(self, name: str) -> None:
        """Timestamped marker in scenario.json."""
        self.meta["phases"].append({"t_ns": time.time_ns(), "name": name})
        print(f"  [{self.scenario}] {name}", flush=True)

    def check(self, name: str, ok: bool, detail: Any = "") -> None:
        """Record a scenario-specific check."""
        self.meta["checks"].append({"name": name, "pass": bool(ok), "detail": detail})
        print(f"  [{self.scenario}] check {'PASS' if ok else 'FAIL'}: {name} {detail}", flush=True)

    def end_window(self, settle_s: float = 2.0) -> None:
        """Close the evaluation window after letting in-flight notifications arrive."""
        time.sleep(settle_s)
        self.meta["t_end_ns"] = time.time_ns()
        time.sleep(settle_s)  # clients keep listening a bit past the window end

    def stop(self) -> None:
        """Quit the equipment first, then the clients; verify no port is left in use."""
        if self.ua is not None:
            self.ua.close()
        try:
            print(f"  [{self.scenario}] equipment: {send_control_command('quit', timeout=5)}", flush=True)
            if self.eq is not None:
                self.eq.wait(30)
        except (OSError, subprocess.TimeoutExpired):
            kill_tree(self.eq)
        time.sleep(0.5)
        for proc in (self.gem, self.uac):
            kill_tree(proc)
        kill_tree(self.eq)
        try:
            wait_for(lambda: not busy_ports(), 15, what="ports to be released")
        except TimeoutError:
            print(f"  [{self.scenario}] WARNING ports still busy: {busy_ports()}", flush=True)
        (self.dir / "scenario.json").write_text(json.dumps(self.meta, indent=1, default=str), encoding="utf-8")

    # ---- helpers for scenario bodies
    def ctl(self, cmd: str) -> str:
        """Operator console command via the control socket."""
        return send_control_command(cmd)

    def status(self) -> dict[str, Any]:
        """Core snapshot."""
        return json.loads(self.ctl("status"))

    def records(self, side: str) -> list[dict[str, Any]]:
        """Current receive log of a client."""
        name = config.GEM_HOST_LOG_FILE if side == "GEM" else config.UA_CLIENT_LOG_FILE
        return checker.load_jsonl(self.dir / name)


# ---------------------------------------------------------------------- scenarios
def s1(run: Run) -> None:
    """S1 normal: 60 s idle with periodic CEID 1007."""
    run.phase("idle 60 s")
    time.sleep(60)
    run.end_window()


def s2(run: Run) -> None:
    """S2 alarm: REMOTE, GEM START, wait overtemp, GEM STOP, wait clear."""
    run.check("console remote", run.ctl("remote").startswith("OK"))
    r = GemRelay.call("start")
    run.check("GEM START -> HCACK 0", r.get("code") == 0, r)
    run.phase("heating")
    waited = wait_for(lambda: bool(run.status()["alarms_active"]), 90, 0.2, "alarm set")
    run.phase(f"alarm 5001 set after {waited:.1f} s")
    time.sleep(1.0)
    r = GemRelay.call("stop")
    run.check("GEM STOP -> HCACK 0", r.get("code") == 0, r)
    waited = wait_for(lambda: not run.status()["alarms_active"], 90, 0.2, "alarm clear")
    run.phase(f"alarm 5001 cleared after {waited:.1f} s")
    run.end_window()
    audit = checker.load_jsonl(run.dir / config.CORE_AUDIT_FILE)
    core_alarms = [(r["kind"], r["seq"]) for r in audit if r["kind"].startswith("alarm_")]
    for side in ("GEM", "UA"):
        got = [(r["kind"], r["seq"]) for r in run.records(side) if r.get("kind", "").startswith("alarm_")]
        run.check(f"{side} saw alarm set+clear with the core's seqs", got == core_alarms, f"{got} vs core {core_alarms}")


def s3(run: Run, rounds: int = 50) -> None:
    """S3 command conflict: REMOTE, GEM START + UA Start at the same instant, 50x; then LOCAL -> HCACK 2."""
    assert run.ua is not None
    run.check("console remote", run.ctl("remote").startswith("OK"))
    clean = 0
    for i in range(1, rounds + 1):
        seq_before = run.status()["last_seq"]
        gem, ua_status, t0, t1 = race("start", None, "Start", (), run.ua)
        run.meta["rounds"].append({"i": i, "action": "START", "seq_before": seq_before, "t0_ns": t0, "t1_ns": t1,
                                   "gem_code": gem.get("code"),
                                   "ua_status": ua_status, "expected_winner": "GEM_HOST"})
        clean += gem.get("code") == 0 and ua_status == "BadUserAccessDenied"
        stop = GemRelay.call("stop")
        if stop.get("code") != 0:
            run.check(f"round {i} reset STOP", False, stop)
        wait_for(lambda: run.status()["processing_state"] == "IDLE", 10, 0.05, "IDLE")
        time.sleep(0.05)
    run.phase(f"{rounds} conflict rounds done")
    run.check(f"{rounds}/{rounds} rounds: GEM HCACK 0 and UA BadUserAccessDenied", clean == rounds, f"{clean} clean")
    run.check("console local", run.ctl("local").startswith("OK"))
    r = GemRelay.call("start")
    run.check("LOCAL: GEM START -> HCACK 2", r.get("code") == config.HCACK_CANNOT_PERFORM_NOW, r)
    run.end_window()


def s4(run: Run, rounds: int = 10) -> None:
    """S4 EC conflict: REMOTE GEM 35 vs UA 45 (only GEM applied), then OFFLINE + lease: UA 45 applied, GEM sees 1006."""
    assert run.ua is not None
    run.check("console remote", run.ctl("remote").startswith("OK"))
    for i in range(1, rounds + 1):
        GemRelay.call("set-limit", 40.0)  # reset
        seq_before = run.status()["last_seq"]
        gem, ua_status, t0, t1 = race("set-limit", 35.0, "SetTempHighLimit",
                                      (ua.Variant(45.0, ua.VariantType.Double),), run.ua)
        run.meta["rounds"].append({"i": i, "action": "EC_WRITE", "seq_before": seq_before, "t0_ns": t0, "t1_ns": t1,
                                   "gem_code": gem.get("code"),
                                   "ua_status": ua_status, "expected_winner": "GEM_HOST"})
    time.sleep(0.5)
    core_limit = run.status()["temp_high_limit"]
    ua_limit = run.ua.read("EquipmentConstants.TempHighLimit")
    gem_limit = GemRelay.call("status")["values"]["TempHighLimit"]
    run.check("REMOTE conflict: final limit 35 in core, GEM (S2F13) and UA",
              core_limit == 35.0 and abs(gem_limit - 35.0) < 1e-3 and ua_limit == 35.0,
              f"core {core_limit}, GEM {gem_limit}, UA {ua_limit}")
    run.check("console offline", run.ctl("offline").startswith("OK"))
    run.check("console lease ua", run.ctl("lease ua").startswith("OK"))
    t_write = time.time_ns()
    status = run.ua.call("SetTempHighLimit", ua.Variant(45.0, ua.VariantType.Double))
    run.check("leased UA SetTempHighLimit(45) -> Good", status == "Good", status)
    time.sleep(1.0)
    seen = [r for r in run.records("GEM") if r.get("kind") == "event" and r.get("id") == config.CEID_TEMP_HIGH_LIMIT_CHANGED
            and r["ts_ns"] >= t_write]
    run.check("GEM host received CEID 1006 with 201=45 (UA's change)",
              any(abs(float(r["data"].get(str(config.ECID_TEMP_HIGH_LIMIT), 0)) - 45.0) < 1e-3 for r in seen),
              [r["data"] for r in seen])
    r = GemRelay.call("set-limit", 30.0)
    run.check("leased: GEM S2F15 -> EAC 2", r.get("code") == config.EAC_DENIED, r)
    time.sleep(0.5)
    run.check("final limit 45 in core and UA", run.status()["temp_high_limit"] == 45.0
              and run.ua.read("EquipmentConstants.TempHighLimit") == 45.0)
    run.check("console lease off", run.ctl("lease off").startswith("OK"))
    run.check("console local", run.ctl("local").startswith("OK"))
    run.end_window()


def s5(run: Run, down_s: float = 10.0) -> None:
    """S5 disconnect: normal running, kill the GEM host for 10 s, reconnect; losses must be attributed (I6)."""
    time.sleep(10)
    run.phase("killing GEM host")
    t_kill = time.time_ns()
    run.kill_gem()
    time.sleep(down_s)
    run.phase("restarting GEM host")
    t_restart = time.time_ns()
    run.start_gem()
    run.phase("GEM host listening again")
    time.sleep(10)
    run.end_window()
    audit = checker.load_jsonl(run.dir / config.CORE_AUDIT_FILE)
    link = [(r["value"], (r["ts_ns"] - t_kill) / 1e6) for r in audit if r["id"] == "GemCommunicationState"
            and r["ts_ns"] >= t_kill]
    run.meta["findings"].append(
        f"GEM link transitions after the kill (value, ms after kill): {[(v, round(ms)) for v, ms in link]}")
    run.meta["kill_ns"], run.meta["restart_ns"] = t_kill, t_restart


def s6(run: Run) -> None:
    """S6 report scope: the GEM host redefines CEID 1007's report without EventTemp; UA fields must not change."""
    assert run.ua is not None
    time.sleep(8)
    run.phase("GEM host redefines report 1007 = [EventSeq] only")
    t_redef = time.time_ns()
    r = GemRelay.call("set-report", ceid=config.CEID_TEMP_SAMPLE, vids=[config.DVID_EVENT_SEQ])
    t_done = time.time_ns()  # events received between t_redef and t_done may use either report: not compared
    run.check("set-report accepted", r.get("code") == 0, r)
    # A second, independent UA subscription that selects ONLY two fields: per-client filtering in UA.
    narrow = run.ua.run(_narrow_subscription)
    time.sleep(8)
    narrow_fields = run.ua.run(lambda s: _narrow_result(s, narrow))
    run.end_window()

    def field_sets(side: str, before: bool) -> set[tuple[str, ...]]:
        out = set()
        for rec in run.records(side):
            if rec.get("kind") == "event" and rec.get("id") == config.CEID_TEMP_SAMPLE \
                    and (rec["ts_ns"] < t_redef) == before:
                data = rec["data"] if side == "GEM" else rec["data"]["payload"]
                out.add(tuple(sorted(data)))
        return out

    gb, ga, ub, uaf = field_sets("GEM", True), field_sets("GEM", False), field_sets("UA", True), field_sets("UA", False)
    run.check("GEM CEID 1007 fields before redefinition = {101, 102}", gb == {("101", "102")}, sorted(gb))
    run.check("GEM CEID 1007 fields after redefinition = {101}", ga == {("101",)}, sorted(ga))
    run.check("UA listener CEID 1007 fields unchanged {101, 102}", ub == uaf == {("101", "102")},
              f"before {sorted(ub)}, after {sorted(uaf)}")
    run.check("2nd UA subscription received only the 2 fields it selected", narrow_fields.get("ok", False), narrow_fields)
    run.meta["findings"].append(
        "GEM report definitions (S2F33/35/37) live on the equipment and apply to the GEM interface as a whole: the "
        "redefinition by one host changed what every later S6F11 for CEID 1007 carries. OPC UA field selection is a "
        "per-subscription EventFilter: one UA client narrowing its fields did not change another UA client's fields.")


async def _narrow_subscription(sess: UaSession) -> dict[str, Any]:
    """Subscribe to Chamber1Tool events selecting only EventSeq and CEID of GemCollectionEventType."""
    assert sess.client is not None
    etype = await sess.client.get_node(ua.ObjectIds.BaseEventType).get_child(f"{sess.idx}:GemCollectionEventType")
    got: list[Any] = []

    class H:
        def event_notification(self, event: Any) -> None:
            got.append(event)

    evfilter = ua.EventFilter()
    for name in ("EventSeq", "CEID"):
        op = ua.SimpleAttributeOperand()
        op.TypeDefinitionId = etype.nodeid
        op.BrowsePath = [ua.QualifiedName(name, sess.idx)]
        op.AttributeId = ua.AttributeIds.Value
        evfilter.SelectClauses.append(op)
    sub = await sess.client.create_subscription(50, H())
    await sub.subscribe_events(sess.node(""), etype, evfilter=evfilter)
    return {"sub": sub, "got": got}


async def _narrow_result(sess: UaSession, narrow: dict[str, Any]) -> dict[str, Any]:
    got = narrow["got"]
    await narrow["sub"].delete()
    fields = sorted({k for e in got for k in e.get_event_props_as_fields_dict()})
    return {"ok": bool(got) and fields == ["CEID", "EventSeq"], "events": len(got), "fields": fields}


def s5_post(meta: dict[str, Any], results: list[checker.Result]) -> None:
    """S5 expected finding, judged from the checker's I6 attribution."""
    i6 = {r.side: r for r in results if r.invariant == "I6"}
    gem, uax = i6["GEM"].metrics, i6["UA"].metrics
    gem_ok = gem["lost"] > 0 and not gem["unexplained"] and set(gem["causes"]) <= {"dropped_no_link", "dropped_disabled", "error"}
    meta["checks"].append({"name": "GEM missed the gap's events, every loss attributed by the GEM send log",
                           "pass": gem_ok, "detail": gem["causes"]})
    meta["checks"].append({"name": "UA missed no event", "pass": uax["lost"] == 0, "detail": uax["causes"]})
    meta["findings"].append(
        f"No spooling: while the GEM host was down the GEM door dropped {gem['lost']} events "
        f"({gem['causes']}); after reconnection they were NOT re-sent. The UA client, unaffected, missed {uax['lost']}.")


def s4_post(meta: dict[str, Any], results: list[checker.Result]) -> None:
    """S4 finding: same-value EC writes are events in GEM but invisible to a UA data-change subscription."""
    i4 = {r.side: r for r in results if r.invariant == "I4"}
    n = i4["UA"].metrics.get("noop_writes", 0) if i4["UA"].metrics else 0
    if n:
        meta["findings"].append(
            f"Semantic mismatch: {n} accepted EC write(s) re-wrote TempHighLimit with the value it already had. "
            "GEM reported each one as CEID 1006 (an event per accepted write). The OPC UA client got no data-change "
            "notification (default DataChangeTrigger StatusValue reports value changes only), so a UA client cannot "
            "observe such a write through the variable. The core and both sides still agreed on the value (I4 PASS).")


POST: dict[str, Callable[[dict[str, Any], list[checker.Result]], None]] = {"S4": s4_post, "S5": s5_post}

SCENARIOS: dict[str, tuple[Callable[[Run], None], str]] = {
    "S1": (s1, "Normal operation: 60 s idle in ONLINE_LOCAL with periodic CEID 1007 (1 Hz)."),
    "S2": (s2, "Alarm: REMOTE, GEM START, wait for ALID 5001 set, GEM STOP, wait for clear."),
    "S3": (s3, "Command conflict: REMOTE; GEM START and UA Start released by one barrier, 50 rounds (GEM STOP "
               "between); then LOCAL and GEM START must get HCACK 2."),
    "S4": (s4, "EC conflict: REMOTE, GEM sets 35 while UA sets 45 (10 barrier rounds) -> only GEM applied; then "
               "OFFLINE + lease ua: UA sets 45 -> applied and seen by GEM as CEID 1006; GEM write -> EAC 2."),
    "S5": (s5, "Disconnect: normal running, the GEM host process is killed for 10 s and restarted. Expected finding: "
               "GEM misses the events of the gap (no spooling), all attributed; UA misses none."),
    "S6": (s6, "Report scope: the GEM host redefines CEID 1007's report to drop EventTemp; the UA listener's event "
               "fields must stay unchanged; a second UA subscription selects only 2 fields."),
}


def run_scenario(name: str, out_dir: Path) -> tuple[str, list[checker.Result], Path]:
    """Run one scenario end to end and write its reports."""
    fn, desc = SCENARIOS[name]
    print(f"=== {name}: {desc}", flush=True)
    run = Run(name, desc)
    try:
        run.start()
        fn(run)
    except Exception as exc:  # noqa: BLE001 - record and still shut down cleanly
        run.check("scenario completed without exception", False, repr(exc))
        run.meta.setdefault("t_end_ns", time.time_ns())
    finally:
        run.stop()
    data = checker.RunData.load(run.dir)
    results = checker.check_run(data)
    if name in POST:  # scenario-specific checks that need the checker's results
        POST[name](run.meta, results)
        (run.dir / "scenario.json").write_text(json.dumps(run.meta, indent=1, default=str), encoding="utf-8")
        data = checker.RunData.load(run.dir)
    md = checker.write_reports(data, results, out_dir)
    checks_ok = all(c["pass"] for c in run.meta["checks"])
    verdict = "PASS" if checker.overall(results) == "PASS" and checks_ok else "FAIL"
    for r in results:
        print(f"  {r.invariant:3} {r.side:5} {r.status:4} {r.detail}", flush=True)
    print(f"=== {name}: {verdict} -> {md}", flush=True)
    return verdict, results, run.dir


def write_overview(rows: list[tuple[str, str, list[checker.Result], Path]], out_dir: Path) -> Path:
    """results/summary.md: one table over all scenarios run in this invocation."""
    order = [("I1", "GEM"), ("I1", "UA"), ("I2", "GEM"), ("I2", "UA"), ("I3", "GEM"), ("I3", "UA"),
             ("I4", "GEM"), ("I4", "UA"), ("I5", "both"), ("I6", "GEM"), ("I6", "UA")]
    head = "| Scenario | " + " | ".join(f"{i} {s}" for i, s in order) + " | Scenario checks | Run |"
    lines = ["# Scenario results overview", "", head, "|" + "---|" * (len(order) + 3)]
    for name, _verdict, results, run_dir in rows:
        by = {(r.invariant, r.side): r.status for r in results}
        meta = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
        checks = meta.get("checks", [])
        n_ok = sum(c["pass"] for c in checks)
        lines.append(f"| [{name}]({name}_summary.md) | " + " | ".join(by.get(k, "—") for k in order)
                     + f" | {n_ok}/{len(checks)} | `{run_dir.name}` |")
    lines += ["", f"> {checker.LATENCY_CAVEAT}", ""]
    path = out_dir / "summary.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="Run consistency scenarios S1..S6")
    ap.add_argument("scenarios", nargs="+", help="S1..S6 or all")
    ap.add_argument("--out", default=config.RESULTS_DIR)
    args = ap.parse_args(argv)
    names = list(ORDER) if "all" in [s.lower() for s in args.scenarios] else [s.upper() for s in args.scenarios]
    out_dir = Path(args.out)
    rows = []
    for name in names:
        verdict, results, run_dir = run_scenario(name, out_dir)
        rows.append((name, verdict, results, run_dir))
    existing = {r[0] for r in rows}
    # Merge with earlier results so summary.md always lists every scenario that has a run.
    for name in ORDER:
        if name in existing:
            continue
        runs = sorted((Path.cwd() / config.RUNS_DIR).glob(f"{name}_*"))
        if runs and (runs[-1] / "scenario.json").exists():
            data = checker.RunData.load(runs[-1])
            res = checker.check_run(data)
            rows.append((name, checker.overall(res), res, runs[-1]))
    rows.sort(key=lambda r: ORDER.index(r[0]))
    print(f"overview -> {write_overview(rows, out_dir)}")
    return 0 if all(r[1] == "PASS" for r in rows if r[0] in names) else 1


if __name__ == "__main__":
    sys.exit(main())
