# harness/demo.py
# Narrated panel demo: press Enter between steps; each step prints one line explaining what will happen and
# why it matters, then runs it and shows the evidence. It starts the equipment and both listening clients itself
# (and, on Windows, the live view in its own console window), and always shuts everything down cleanly.
# Serves N1 (arbiter in action), N2 (self-describing model) and N3 (checker verdict on the demo run itself).
"""python -m harness.demo [--auto] [--no-live-window] [--web [--web-port 8080] [--no-browser]]"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import webbrowser
from typing import Any, Optional

from equipment import config
from harness import checker
from harness.scenarios import PY, GemRelay, Run, busy_ports, kill_tree, race, wait_for

AUTO = False


def say(step: str, line: str) -> None:
    """Print the step header and its one-line explanation, then wait for Enter."""
    print(f"\n\033[1m=== {step}\033[0m\n{line}", flush=True)
    if not AUTO:
        input("   [Enter] ")


def show(text: str) -> None:
    """Indented output."""
    for line in str(text).splitlines():
        print(f"   {line}", flush=True)


def last(run: Run, side: str, kinds: tuple[str, ...]) -> Optional[dict[str, Any]]:
    """Most recent record of given kinds in a client's receive log."""
    recs = [r for r in run.records(side) if r.get("kind") in kinds]
    return recs[-1] if recs else None


def start_live_window(run: Run) -> Optional[subprocess.Popen]:
    """Windows: open the live view in its own console window (elsewhere: print how to start it)."""
    cmd = [PY, "-m", "harness.live_view", "--run-id", run.run_id]
    if os.name == "nt":
        return subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE,  # type: ignore[attr-defined]
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    show(f"open another terminal and run:  {' '.join(cmd[1:])}  (python -m ...)")
    return None


def start_web(run: Run, port: int, open_browser: bool) -> subprocess.Popen:
    """Start the read-only web dashboard on this demo's run folder (it waits until the folder exists)."""
    proc = subprocess.Popen([PY, "-m", "harness.web_view", "--run-dir", str(run.dir), "--port", str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    url = f"http://localhost:{port}/"
    wait_for(lambda: _port_open(port), 15, what="web dashboard")
    if open_browser:
        webbrowser.open(url)
    show(f"web dashboard: {url}")
    return proc


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def demo(live_window: bool, web: bool = False, web_port: int = 8080, open_browser: bool = True) -> int:
    """The narrated sequence."""
    if busy_ports():
        print(f"ports {busy_ports()} are in use: stop the running equipment/clients first", file=sys.stderr)
        return 1
    if web and _port_open(web_port):
        print(f"port {web_port} is in use (another web_view?): stop it or pass --web-port", file=sys.stderr)
        return 1
    run = Run("DEMO", "Narrated panel demo (harness/demo.py)")
    live: Optional[subprocess.Popen] = None
    try:
        if web:  # started before the equipment so the page shows the run from its first record
            live = start_web(run, web_port, open_browser)
        say("0. Start", "One simulated chamber, ONE core, two doors: SECS/GEM on port 5000 and OPC UA on port 4840. "
                        "A scripted GEM host and an OPC UA client both connect and log everything they receive.")
        run.start()
        show(f"run id {run.run_id}: equipment, GEM host and OPC UA client are up; logs in runs/{run.run_id}/")
        if live_window and not web:
            live = start_live_window(run)
            show("live view: GEM host sees | Core (truth) | OPC UA client sees")

        say("1. Browse the OPC UA model",
            "The OPC UA side describes itself: types first, then the instance; every GEM-mapped node carries its GEM ID.")
        out = subprocess.run([PY, "-m", "clients.ua_client", "--browse"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        show(out.stdout.strip())

        say("2. Operator: REMOTE", "The operator hands command authority to the fab host (GEM). The core audits it "
                                   "and BOTH doors announce it: CEID 1001/1004 on GEM, ControlState/Authority on UA.")
        show(f"console remote -> {run.ctl('remote')}")
        snap = run.status()
        show(f"core: {snap['control_state']}, authority {snap['authority']}")

        say("3. GEM host: START", "S2F41 START goes through the arbiter: in REMOTE the GEM host holds authority, so HCACK 0.")
        show(f"S2F42 -> {GemRelay.call('start')}")

        say("4. Over-temperature alarm on both sides",
            "The heater runs; when the chamber passes TempHighLimit (40 °C) ALID 5001 is set ONCE in the core, "
            "and both interfaces receive it with the same sequence number.")
        t0 = time.monotonic()
        while not run.status()["alarms_active"]:
            print(f"\r   heating... {run.status()['temp']:.2f} °C  ({time.monotonic() - t0:.0f} s)  ", end="", flush=True)
            time.sleep(0.5)
        print()
        time.sleep(1.0)
        g, u = last(run, "GEM", ("alarm_set",)), last(run, "UA", ("alarm_set",))
        core_alarm = [r for r in checker.load_jsonl(run.dir / config.CORE_AUDIT_FILE) if r["kind"] == "alarm_set"][-1]
        show(f"core : alarm_set seq {core_alarm['seq']} at {core_alarm['value']:.2f} °C")
        show(f"GEM  : S5F1 '{g['data']['text'] if g else '-'}'")
        show(f"UA   : GemOffNormalAlarmType event, EventSeq {u['seq'] if u else '-'}, "
             f"'{u['data']['message'] if u else '-'}'")
        show(f"GEM STOP (to make the next step possible) -> {GemRelay.call('stop')}")
        wait_for(lambda: run.status()["processing_state"] == "IDLE", 10)

        say("5. Simultaneous START from both interfaces",
            "GEM START and UA Start are released by one barrier at the same instant. The arbiter decides atomically: "
            "exactly one wins, and it is GEM because REMOTE gives GEM authority - not because it was faster.")
        assert run.ua is not None
        seq_before = run.status()["last_seq"]
        gem, ua_status, t_a, t_b = race("start", None, "Start", (), run.ua)
        run.meta["rounds"].append({"i": 1, "action": "START", "seq_before": seq_before, "t0_ns": t_a, "t1_ns": t_b,
                                   "gem_code": gem.get("code"), "ua_status": ua_status, "expected_winner": "GEM_HOST"})
        audit = checker.load_jsonl(run.dir / config.CORE_AUDIT_FILE)
        rd = checker.round_records(checker.RunData(run.dir, audit, {"GEM": [], "UA": []}, {"GEM": [], "UA": []},
                                                   {}), run.meta["rounds"][-1])
        show(f"GEM HCACK {gem.get('code')}   |   UA {ua_status}")
        show("arrival order at the core: " + " then ".join(f"{r['origin']} ({r['kind']}, seq {r['seq']})" for r in rd))
        time.sleep(0.5)
        loser_1005 = [r for r in checker.load_jsonl(run.dir / config.CORE_AUDIT_FILE)
                      if r["kind"] == "event" and r["id"] == config.CEID_COMMAND_REJECTED][-1]
        seen = {side: any(r.get("seq") == loser_1005["seq"] for r in run.records(side)) for side in ("GEM", "UA")}
        show(f"the loser's rejection is CEID 1005 seq {loser_1005['seq']} "
             f"({loser_1005['value'][str(config.DVID_REJECT_REASON)]}); received by GEM: {seen['GEM']}, UA: {seen['UA']}")
        show(f"GEM STOP -> {GemRelay.call('stop')}")
        wait_for(lambda: run.status()["processing_state"] == "IDLE", 10)

        say("6. Operator: LOCAL, then GEM START", "Authority goes back to the operator. The same GEM command is now "
                                                  "refused with HCACK 2, and the refusal is visible on both sides.")
        show(f"console local -> {run.ctl('local')}")
        show(f"S2F42 -> {GemRelay.call('start')}")
        show(f"core last rejection: {run.status()['last_rejection']}")

        say("7. Kill the GEM host for 10 s, then reconnect",
            "Simulates a host crash. SECS/GEM here has no spooling: events during the outage are dropped by the GEM door "
            "and recorded as dropped_no_link; the OPC UA client keeps receiving everything.")
        t_kill = time.time_ns()
        run.kill_gem()
        for k in range(10, 0, -1):
            print(f"\r   GEM host down... {k:2d} s ", end="", flush=True)
            time.sleep(1)
        print()
        run.start_gem()
        send = checker.load_jsonl(run.dir / config.GEM_SEND_LOG_FILE)
        dropped = sum(1 for r in send if r["outcome"] == "dropped_no_link" and r["ts_ns"] >= t_kill)
        show(f"GEM host reconnected; GEM door recorded {dropped} events as dropped_no_link during the outage")
        time.sleep(3)

        say("8. Checker verdict on THIS demo run",
            "The checker joins the core audit (the oracle) with both receive logs and both send logs by seq.")
        run.end_window()
    except KeyboardInterrupt:
        print("\ninterrupted - shutting down")
    finally:
        run.stop()
        kill_tree(live)
    if "t_end_ns" not in run.meta:
        return 1
    data = checker.RunData.load(run.dir)
    results = checker.check_run(data)
    md = checker.write_reports(data, results, run.dir / "report")
    for r in results:
        print(f"   {r.invariant:3} {r.side:5} {r.status:4} {r.detail}")
    for side in checker.SIDES:
        lt = checker.latency(data, side)
        print(f"   latency {side}: p50 {lt.get('p50_ms')} ms, p95 {lt.get('p95_ms')} ms, max {lt.get('max_ms')} ms")
    print(f"\n   overall {checker.overall(results)}   (report: {md})")
    print(f"   all ports released: {not busy_ports()}")
    return 0 if checker.overall(results) == "PASS" else 1


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    global AUTO
    ap = argparse.ArgumentParser(description="Narrated panel demo")
    ap.add_argument("--auto", action="store_true", help="do not wait for Enter between steps")
    ap.add_argument("--no-live-window", action="store_true", help="do not open the live view window")
    ap.add_argument("--web", action="store_true", help="show the web dashboard instead of the terminal live view")
    ap.add_argument("--web-port", type=int, default=8080)
    ap.add_argument("--no-browser", action="store_true", help="--web: do not open a browser tab")
    args = ap.parse_args(argv)
    AUTO = args.auto
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    if os.name == "nt":
        os.system("")  # enable ANSI escape codes in the Windows console
    return demo(live_window=not args.no_live_window, web=args.web, web_port=args.web_port,
                open_browser=not args.no_browser)


if __name__ == "__main__":
    sys.exit(main())
