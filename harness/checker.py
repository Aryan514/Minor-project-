# harness/checker.py
# The consistency checker: evaluates invariants I1-I6 (docs/invariants.md) for one run by joining the core
# audit log (the oracle, by seq) with each client's receive log and each door's send log, and reports latency.
# `--self-test` corrupts a COPY of a real run in known ways (drop / swap / change value / delay / double winner)
# and proves each corruption is flagged, i.e. that the checker can actually fail.
# Serves N3 (cross-interface consistency test method).
"""Invariant checker for one run directory (python -m harness.checker <run_id|path> [--self-test])."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import statistics
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from equipment import config

EVENT_KINDS = ("event", "alarm_set", "alarm_clear")
SIDES = ("GEM", "UA")
LOSS_EXPLANATIONS = ("dropped_no_link", "dropped_disabled", "error", "dropped_queue")
LATENCY_CAVEAT = (
    "Latency = client receive time - core audit time, both `time.time_ns()` on the same laptop (loopback). "
    "The UA figure includes the client's 50 ms subscription publishing interval, and GEM sees the temperature "
    "only through the 1 Hz CEID 1007. These numbers describe this setup. They must not be read as one protocol "
    "being faster than the other."
)


# ---------------------------------------------------------------------- loading
def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file; a missing file or a torn last line is tolerated."""
    out: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except FileNotFoundError:
        pass
    return out


@dataclass
class Session:
    """One connection period of a listening client."""

    start_ns: int
    listen_ns: Optional[int] = None
    end_ns: Optional[int] = None
    stopped: bool = False


@dataclass
class RunData:
    """Everything the checker reads for one run."""

    run_dir: Path
    audit: list[dict[str, Any]]
    client: dict[str, list[dict[str, Any]]]
    send: dict[str, list[dict[str, Any]]]
    scenario: dict[str, Any]

    @classmethod
    def load(cls, run_dir: Path) -> "RunData":
        """Load all logs of a run."""
        try:
            scenario = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            scenario = {}
        return cls(
            run_dir=run_dir,
            audit=load_jsonl(run_dir / config.CORE_AUDIT_FILE),
            client={"GEM": load_jsonl(run_dir / config.GEM_HOST_LOG_FILE),
                    "UA": load_jsonl(run_dir / config.UA_CLIENT_LOG_FILE)},
            send={"GEM": load_jsonl(run_dir / config.GEM_SEND_LOG_FILE),
                  "UA": load_jsonl(run_dir / config.UA_SEND_LOG_FILE)},
            scenario=scenario,
        )

    # ---- derived views
    def window(self) -> tuple[int, int]:
        """Evaluation window [t_start, t_end] from scenario.json (default: whole audit)."""
        t0 = self.scenario.get("t_start_ns", self.audit[0]["ts_ns"] if self.audit else 0)
        t1 = self.scenario.get("t_end_ns", self.audit[-1]["ts_ns"] if self.audit else 0)
        return int(t0), int(t1)

    def core_events(self) -> dict[int, dict[str, Any]]:
        """Core event/alarm records inside the evaluation window, by seq."""
        t0, t1 = self.window()
        return {r["seq"]: r for r in self.audit if r["kind"] in EVENT_KINDS and t0 <= r["ts_ns"] <= t1}

    def all_core_events(self) -> dict[int, dict[str, Any]]:
        """Every core event/alarm record, by seq."""
        return {r["seq"]: r for r in self.audit if r["kind"] in EVENT_KINDS}

    def received(self, side: str) -> list[dict[str, Any]]:
        """Client event/alarm records that carry a seq, in file (= arrival) order."""
        return [r for r in self.client[side] if r.get("kind") in EVENT_KINDS and r.get("seq") is not None]

    def sessions(self, side: str) -> list[Session]:
        """Split a client log into sessions at each `connecting` record."""
        out: list[Session] = []
        for r in self.client[side]:
            kind = r.get("kind")
            if kind == "connecting" or (kind == "listening" and (not out or out[-1].listen_ns is not None)):
                out.append(Session(start_ns=r["ts_ns"]))
            if not out:
                continue
            s = out[-1]
            if kind == "listening":
                s.listen_ns = r["ts_ns"]
            if kind == "stopped":
                s.stopped = True
                s.end_ns = r["ts_ns"]
            elif not s.stopped:
                s.end_ns = r["ts_ns"]
        return out

    def in_session(self, side: str, ts_ns: int, margin_ns: int = 0) -> bool:
        """True if a client of `side` was listening at core time ts_ns (with `margin_ns` before session end)."""
        for s in self.sessions(side):
            if s.listen_ns is not None and s.end_ns is not None and s.listen_ns <= ts_ns <= s.end_ns - margin_ns:
                return True
        return False


@dataclass
class Result:
    """One invariant evaluated for one side."""

    invariant: str
    side: str
    status: str  # PASS / FAIL / N/A
    detail: str
    metrics: dict[str, Any] = field(default_factory=dict)


def _num_equal(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(float(a) - float(b)) <= config.FLOAT_TOLERANCE
    return a == b


# ---------------------------------------------------------------------- invariants
def check_i1(run: RunData, side: str) -> Result:
    """I1 Completeness: every core event/alarm in the window, while the client listened, received exactly once."""
    core = run.core_events()
    expected = {s for s, r in core.items() if run.in_session(side, r["ts_ns"])}
    counts = Counter(r["seq"] for r in run.received(side))
    missing = sorted(expected - set(counts))
    dups = sorted(s for s, n in counts.items() if n > 1)
    if not expected:
        return Result("I1", side, "N/A", "no client session inside the window")
    ok = not missing and not dups
    return Result("I1", side, "PASS" if ok else "FAIL",
                  f"expected {len(expected)}, received {len(expected & set(counts))}, missing {len(missing)}, "
                  f"duplicates {len(dups)}" + (f"; missing seqs {missing[:10]}" if missing else ""),
                  {"expected": len(expected), "missing": missing, "duplicates": dups})


def check_i2(run: RunData, side: str) -> Result:
    """I2 Order: seqs arrive strictly increasing (inversions, duplicates and gaps counted)."""
    seqs = [r["seq"] for r in run.received(side)]
    if not seqs:
        return Result("I2", side, "N/A", "nothing received")
    inversions = sum(1 for a, b in zip(seqs, seqs[1:]) if b < a)
    dups = sum(1 for a, b in zip(seqs, seqs[1:]) if b == a)
    core = sorted(run.all_core_events())
    pos = {s: i for i, s in enumerate(core)}
    gaps = sum(1 for a, b in zip(seqs, seqs[1:]) if a in pos and b in pos and pos[b] - pos[a] > 1)
    ok = inversions == 0 and dups == 0
    return Result("I2", side, "PASS" if ok else "FAIL",
                  f"{len(seqs)} received, inversions {inversions}, adjacent duplicates {dups}, gaps {gaps} "
                  "(gaps are judged by I1/I6)", {"inversions": inversions, "duplicates": dups, "gaps": gaps})


def check_i3(run: RunData) -> list[Result]:
    """I3 Value agreement: for each seq, ID/kind and every reported value equal the core (floats 1e-3)."""
    core = run.all_core_events()
    results = []
    for side in SIDES:
        mismatches: list[str] = []
        fields_missing: Counter[int] = Counter()
        compared = 0
        for r in run.received(side):
            c = core.get(r["seq"])
            if c is None:
                mismatches.append(f"seq {r['seq']} not in core audit")
                continue
            compared += 1
            if r["kind"] != c["kind"] or int(r["id"]) != int(c["id"]):
                mismatches.append(f"seq {r['seq']}: {r['kind']} {r['id']} vs core {c['kind']} {c['id']}")
                continue
            if c["kind"] != "event":
                continue
            got = r["data"] if side == "GEM" else r["data"].get("payload", {})
            for vid, cval in c["value"].items():
                if vid not in got:
                    fields_missing[int(c["id"])] += 1
                elif not _num_equal(got[vid], cval):
                    mismatches.append(f"seq {r['seq']} CEID {c['id']} VID {vid}: {got[vid]!r} vs core {cval!r}")
        if compared == 0:
            results.append(Result("I3", side, "N/A", "nothing received"))
            continue
        detail = f"{compared} compared, {len(mismatches)} mismatches"
        if fields_missing:
            detail += f"; report fields absent (not values that disagree): {dict(fields_missing)} per CEID"
        if mismatches:
            detail += f"; e.g. {mismatches[:3]}"
        results.append(Result("I3", side, "FAIL" if mismatches else "PASS", detail,
                              {"compared": compared, "mismatches": mismatches,
                               "fields_missing": dict(fields_missing)}))
    return results


_STATE_KEYS = {"ControlState", "ProcessingState"}


def state_changes(run: RunData) -> list[dict[str, Any]]:
    """Core state changes in the window that clients can observe."""
    t0, t1 = run.window()
    out = []
    for r in run.audit:
        if not (t0 <= r["ts_ns"] <= t1):
            continue
        if (r["kind"] == "state" and r["id"] in _STATE_KEYS) or r["kind"] == "authority":
            out.append({"key": r["id"], "value": r["value"], "seq": r["seq"], "ts_ns": r["ts_ns"],
                        "num": r.get("extra", {}).get("id")})
        elif r["kind"] == "ec_write":
            out.append({"key": "TempHighLimit", "value": r["value"], "seq": r["seq"], "ts_ns": r["ts_ns"], "num": None})
    return out


def _gem_observation(run: RunData, ch: dict[str, Any]) -> Optional[int]:
    """Receive time of the GEM event that tells the host about this change."""
    key = ch["key"]
    for r in run.received("GEM"):
        if r["seq"] <= ch["seq"] or r["kind"] != "event":
            continue
        d, ceid = r["data"], int(r["id"])
        if key == "ControlState" and ceid == config.CEID_CONTROL_STATE_CHANGED \
                and d.get(str(config.SVID_CONTROL_STATE)) == ch["num"]:
            return r["ts_ns"]
        if key == "ProcessingState" and ceid == (config.CEID_PROCESSING_STARTED if ch["value"] == "EXECUTING"
                                                  else config.CEID_PROCESSING_STOPPED):
            return r["ts_ns"]
        if key == "Authority" and ceid == config.CEID_AUTHORITY_CHANGED \
                and d.get(str(config.SVID_AUTHORITY)) == ch["value"]:
            return r["ts_ns"]
        if key == "TempHighLimit" and ceid == config.CEID_TEMP_HIGH_LIMIT_CHANGED \
                and _num_equal(d.get(str(config.ECID_TEMP_HIGH_LIMIT)), ch["value"]):
            return r["ts_ns"]
    return None


def _ua_observation(run: RunData, ch: dict[str, Any]) -> Optional[int]:
    """Receive time of the UA data change written for this exact core record (SourceTimestamp = core ts)."""
    for r in run.client["UA"]:
        if r.get("kind") != "data" or r.get("id") != ch["key"]:
            continue
        src = (r.get("data") or {}).get("source_ts_ns")
        if src is not None and abs(src - ch["ts_ns"]) < 2_000 and _num_equal(r["data"]["value"], ch["value"]):
            return r["ts_ns"]
    return None


def check_i4(run: RunData) -> list[Result]:
    """I4 State convergence: each state change is reported by both sides within T = 500 ms."""
    limit_ns = config.STATE_CONVERGENCE_T_MS * 1_000_000
    changes = state_changes(run)
    results = []
    for side in SIDES:
        observe = _gem_observation if side == "GEM" else _ua_observation
        lat, late, never = [], [], []
        for ch in changes:
            if not run.in_session(side, ch["ts_ns"], margin_ns=limit_ns):
                continue
            t = observe(run, ch)
            if t is None:
                never.append(f"seq {ch['seq']} {ch['key']}={ch['value']}")
                continue
            ms = (t - ch["ts_ns"]) / 1e6
            lat.append(ms)
            if ms > config.STATE_CONVERGENCE_T_MS:
                late.append(f"seq {ch['seq']} {ch['key']} after {ms:.0f} ms")
        if not lat and not never:
            results.append(Result("I4", side, "N/A", "no state change while the client listened"))
            continue
        ok = not late and not never
        detail = (f"{len(lat) + len(never)} changes, max {max(lat):.1f} ms" if lat else f"{len(never)} changes")
        if late or never:
            detail += f"; late {late[:3]}; never {never[:3]}"
        results.append(Result("I4", side, "PASS" if ok else "FAIL", detail,
                              {"changes": len(lat) + len(never), "max_ms": max(lat) if lat else None,
                               "late": late, "never": never}))
    return results


def _round_kinds(rd: dict[str, Any]) -> tuple[str, str]:
    return ("command_ok", "command_rejected") if rd["action"] == "START" else ("ec_write", "ec_rejected")


def round_records(run: RunData, rd: dict[str, Any]) -> list[dict[str, Any]]:
    """The conflicting commands of one round: the FIRST record per origin (GEM_HOST, UA_CLIENT) of the round's
    action after `seq_before` (core last_seq read just before the barrier).

    Rounds are anchored on seq, not wall-clock time: on Windows several records share one `time_ns` value, so a
    time window cannot separate the round from the reset command that follows it (found in the first S3 run).
    """
    ok_kind, rej_kind = _round_kinds(rd)
    want_id = "START" if rd["action"] == "START" else str(config.ECID_TEMP_HIGH_LIMIT)
    first: dict[str, dict[str, Any]] = {}
    for r in run.audit:
        if r["seq"] <= rd["seq_before"] or r["origin"] not in ("GEM_HOST", "UA_CLIENT"):
            continue
        if r["kind"] in (ok_kind, rej_kind) and str(r["id"]) == want_id and r["origin"] not in first:
            first[r["origin"]] = r
        if len(first) == 2:
            break
    return sorted(first.values(), key=lambda r: r["seq"])


def check_i5(run: RunData) -> list[Result]:
    """I5 Single winner: per conflict round exactly one accepted; loser gets the mapped code + CEID 1005 on both."""
    rounds = run.scenario.get("rounds", [])
    if not rounds:
        return [Result("I5", "both", "N/A", "no conflict rounds in this scenario")]
    gem_seqs = {r["seq"] for r in run.received("GEM")}
    ua_seqs = {r["seq"] for r in run.received("UA")}
    by_seq = {r["seq"]: r for r in run.audit}
    failures: list[str] = []
    gem_first = 0
    for rd in rounds:
        ok_kind, rej_kind = _round_kinds(rd)
        recs = round_records(run, rd)
        winners = [r for r in recs if r["kind"] == ok_kind]
        losers = [r for r in recs if r["kind"] == rej_kind]
        tag = f"round {rd['i']}"
        if len(recs) == 2 and recs[0]["origin"] == "GEM_HOST":
            gem_first += 1
        if len(winners) != 1 or len(losers) != 1:
            failures.append(f"{tag}: {len(winners)} accepted / {len(losers)} rejected")
            continue
        w, lo = winners[0], losers[0]
        if rd.get("expected_winner") and w["origin"] != rd["expected_winner"]:
            failures.append(f"{tag}: winner {w['origin']}, expected {rd['expected_winner']}")
        gem_code, ua_status = rd.get("gem_code"), rd.get("ua_status")
        if w["origin"] == "GEM_HOST" and (gem_code != 0 or ua_status != config.UA_STATUS_AUTHORITY):
            failures.append(f"{tag}: replies GEM {gem_code} / UA {ua_status}")
        if w["origin"] == "UA_CLIENT" and (ua_status != "Good" or gem_code != config.HCACK_CANNOT_PERFORM_NOW):
            failures.append(f"{tag}: replies GEM {gem_code} / UA {ua_status}")
        ev = by_seq.get(lo["seq"] + 1)
        if not ev or ev["kind"] != "event" or int(ev["id"]) != config.CEID_COMMAND_REJECTED \
                or ev["value"].get(str(config.DVID_ORIGIN)) != lo["origin"]:
            failures.append(f"{tag}: no CEID 1005 right after the rejection")
            continue
        if ev["seq"] not in gem_seqs or ev["seq"] not in ua_seqs:
            failures.append(f"{tag}: CEID 1005 seq {ev['seq']} seen by GEM={ev['seq'] in gem_seqs} "
                            f"UA={ev['seq'] in ua_seqs}")
    detail = (f"{len(rounds)} rounds, {len(rounds) - len({f.split(':')[0] for f in failures})} clean; "
              f"request from GEM reached the core first in {gem_first}/{len(rounds)} rounds")
    if failures:
        detail += f"; {failures[:3]}"
    return [Result("I5", "both", "FAIL" if failures else "PASS", detail,
                   {"rounds": len(rounds), "failures": failures, "gem_arrived_first": gem_first})]


def check_i6(run: RunData, side: str) -> Result:
    """I6 Loss attribution: every window event a client did not get is explained by the send-side log."""
    core = run.core_events()
    got = {r["seq"] for r in run.received(side)}
    send = {r["seq"]: r["outcome"] for r in run.send[side]}
    sub = "gem" if side == "GEM" else "opcua"
    queue_drops = {r["id"] for r in run.audit if r["kind"] == "dropped" and r.get("extra", {}).get("subscriber") == sub}
    causes: Counter[str] = Counter()
    unexplained: list[int] = []
    for seq in sorted(core):
        if seq in got:
            continue
        if seq in queue_drops:
            causes["dropped_queue"] += 1
        elif send.get(seq) in LOSS_EXPLANATIONS:
            causes[send[seq]] += 1
        else:
            unexplained.append(seq)
            causes["unexplained"] += 1
    lost = sum(causes.values())
    detail = f"{lost} of {len(core)} window events not received; causes {dict(causes) or '{}'}"
    if unexplained:
        detail += f"; unexplained seqs {unexplained[:10]} (send log: {[send.get(s, 'absent') for s in unexplained[:5]]})"
    return Result("I6", side, "FAIL" if unexplained else "PASS", detail,
                  {"lost": lost, "causes": dict(causes), "unexplained": unexplained})


def latency(run: RunData, side: str) -> dict[str, Any]:
    """Event latency (client receive ts - core ts) in ms for events inside the window."""
    core = run.core_events()
    vals = sorted((r["ts_ns"] - core[r["seq"]]["ts_ns"]) / 1e6 for r in run.received(side) if r["seq"] in core)
    if not vals:
        return {"side": side, "n": 0}
    p95 = vals[min(len(vals) - 1, int(round(0.95 * (len(vals) - 1))))]
    return {"side": side, "n": len(vals), "p50_ms": round(statistics.median(vals), 2),
            "p95_ms": round(p95, 2), "max_ms": round(vals[-1], 2)}


def check_run(run: RunData) -> list[Result]:
    """All invariants in order I1..I6."""
    res: list[Result] = []
    res += [check_i1(run, s) for s in SIDES]
    res += [check_i2(run, s) for s in SIDES]
    res += check_i3(run)
    res += check_i4(run)
    res += check_i5(run)
    res += [check_i6(run, s) for s in SIDES]
    return res


# ---------------------------------------------------------------------- reporting
def write_reports(run: RunData, results: list[Result], out_dir: Path, title: Optional[str] = None) -> Path:
    """Write <scenario>_summary.md and <scenario>_invariants.csv; return the markdown path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    name = run.scenario.get("scenario", run.run_dir.name)
    lat = [latency(run, s) for s in SIDES]
    with open(out_dir / f"{name}_invariants.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "run_id", "invariant", "side", "status", "detail"])
        for r in results:
            w.writerow([name, run.run_dir.name, r.invariant, r.side, r.status, r.detail])
        for lt in lat:
            w.writerow([name, run.run_dir.name, "latency", lt["side"], "INFO",
                        json.dumps({k: v for k, v in lt.items() if k != "side"})])
    t0, t1 = run.window()
    lines = [f"# {title or name} — results", "",
             f"- Run: `runs/{run.run_dir.name}` (seed {run.scenario.get('seed', '?')})",
             f"- Scenario: {run.scenario.get('description', '')}",
             f"- Evaluation window: {(t1 - t0) / 1e9:.1f} s, {len(run.core_events())} core events/alarms, "
             f"{len(run.audit)} audit records in total", "",
             "## Invariants", "", "| Invariant | Side | Result | Detail |", "|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r.invariant} | {r.side} | **{r.status}** | {r.detail.replace('|', '/')} |")
    checks = run.scenario.get("checks", [])
    if checks:
        lines += ["", "## Scenario-specific checks", "", "| Check | Result | Detail |", "|---|---|---|"]
        for c in checks:
            lines.append(f"| {c['name']} | **{'PASS' if c['pass'] else 'FAIL'}** | {str(c.get('detail', '')).replace('|', '/')} |")
    findings = run.scenario.get("findings", [])
    if findings:
        lines += ["", "## Findings", ""] + [f"- {x}" for x in findings]
    lines += ["", "## Latency (events)", "", "| Side | n | p50 ms | p95 ms | max ms |", "|---|---|---|---|---|"]
    for lt in lat:
        lines.append(f"| {lt['side']} | {lt['n']} | {lt.get('p50_ms', '—')} | {lt.get('p95_ms', '—')} | {lt.get('max_ms', '—')} |")
    lines += ["", f"> {LATENCY_CAVEAT}", ""]
    md = out_dir / f"{name}_summary.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    return md


def overall(results: list[Result]) -> str:
    """PASS if nothing failed."""
    return "FAIL" if any(r.status == "FAIL" for r in results) else "PASS"


# ---------------------------------------------------------------------- self-test
def _rewrite(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _middle_index(items: list[int]) -> int:
    return items[len(items) // 2]


def corrupt(run_dir: Path, mode: str) -> str:
    """Apply one known corruption to a run directory (a COPY!). Returns a description."""
    run = RunData.load(run_dir)
    core = run.core_events()
    if mode == "drop_event":  # GEM host "never received" one event that the door logged as sent
        recs = run.client["GEM"]
        idx = [i for i, r in enumerate(recs) if r.get("kind") == "event" and r.get("seq") in core]
        victim = recs.pop(_middle_index(idx))
        _rewrite(run_dir / config.GEM_HOST_LOG_FILE, recs)
        return f"removed GEM event seq {victim['seq']}"
    if mode == "swap_events":  # UA client receives two events in the wrong order
        recs = run.client["UA"]
        idx = [i for i, r in enumerate(recs) if r.get("kind") == "event" and r.get("seq") in core]
        i, j = idx[len(idx) // 2], idx[len(idx) // 2 + 1]
        recs[i], recs[j] = recs[j], recs[i]
        _rewrite(run_dir / config.UA_CLIENT_LOG_FILE, recs)
        return f"swapped UA events seq {recs[j]['seq']} and {recs[i]['seq']}"
    if mode == "change_value":  # GEM reports a temperature that differs from the core by 1 degC
        recs = run.client["GEM"]
        key = str(config.DVID_EVENT_TEMP)
        idx = [i for i, r in enumerate(recs) if r.get("kind") == "event" and key in (r.get("data") or {})]
        r = recs[_middle_index(idx)]
        r["data"][key] = float(r["data"][key]) + 1.0
        _rewrite(run_dir / config.GEM_HOST_LOG_FILE, recs)
        return f"changed EventTemp of GEM seq {r['seq']} by +1.0"
    if mode == "delay_state":  # UA client sees a state change 2 s late
        ch = state_changes(run)[0]
        recs = run.client["UA"]
        for r in recs:
            if r.get("kind") == "data" and r.get("id") == ch["key"] and \
                    abs((r["data"].get("source_ts_ns") or 0) - ch["ts_ns"]) < 2_000:
                r["ts_ns"] += 2_000_000_000
        _rewrite(run_dir / config.UA_CLIENT_LOG_FILE, recs)
        return f"delayed UA notification of {ch['key']}={ch['value']} (seq {ch['seq']}) by 2 s"
    if mode == "double_winner":  # the core accepts both commands of one conflict round
        rd = run.scenario["rounds"][0]
        target = {r["seq"] for r in round_records(run, rd) if r["kind"] in ("command_rejected", "ec_rejected")}
        for r in run.audit:
            if r["seq"] in target:
                r["kind"] = "command_ok" if r["kind"] == "command_rejected" else "ec_write"
        _rewrite(run_dir / config.CORE_AUDIT_FILE, run.audit)
        return f"turned the rejection in conflict round {rd['i']} into an acceptance"
    raise ValueError(mode)


SELF_TEST_CASES = [  # (corruption, invariants that MUST fail, side)
    ("drop_event", ["I1", "I6"], "GEM"),
    ("swap_events", ["I2"], "UA"),
    ("change_value", ["I3"], "GEM"),
    ("delay_state", ["I4"], "UA"),
    ("double_winner", ["I5"], "both"),
]


def self_test(run_dir: Path) -> tuple[bool, list[dict[str, Any]]]:
    """Baseline must pass; each corruption of a copy must be flagged by its invariant(s)."""
    rows: list[dict[str, Any]] = []
    base = check_run(RunData.load(run_dir))
    rows.append({"case": "baseline (unmodified)", "change": "-", "expected": "all PASS/N/A",
                 "flagged": [f"{r.invariant}/{r.side}" for r in base if r.status == "FAIL"],
                 "ok": overall(base) == "PASS"})
    has_rounds = bool(RunData.load(run_dir).scenario.get("rounds"))
    for mode, must_fail, side in SELF_TEST_CASES:
        if mode == "double_winner" and not has_rounds:
            continue
        with tempfile.TemporaryDirectory(dir=run_dir.parent) as tmp:
            copy = Path(tmp) / run_dir.name
            shutil.copytree(run_dir, copy)
            what = corrupt(copy, mode)
            res = check_run(RunData.load(copy))
        failed = {(r.invariant, r.side) for r in res if r.status == "FAIL"}
        ok = all((inv, side) in failed for inv in must_fail)
        rows.append({"case": mode, "change": what, "expected": ", ".join(f"{i} {side} FAIL" for i in must_fail),
                     "flagged": sorted(f"{i}/{s}" for i, s in failed), "ok": ok})
    return all(r["ok"] for r in rows), rows


def self_test_markdown(run_dir: Path, rows: list[dict[str, Any]]) -> str:
    """Markdown table of a self-test."""
    lines = [f"# Checker self-test on `runs/{run_dir.name}`", "",
             "Each case corrupts a temporary COPY of the run and re-runs the checker. The baseline must pass and "
             "every corruption must be flagged by the invariant it violates. This shows the checker can actually fail.", "",
             "| Case | Corruption applied | Expected | Flagged by checker | OK |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['case']} | {r['change']} | {r['expected']} | {', '.join(r['flagged']) or 'nothing'} | "
                     f"{'yes' if r['ok'] else '**NO**'} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------- CLI
def resolve_run(arg: str) -> Path:
    """Accept a run id (under runs/) or a path."""
    p = Path(arg)
    return p if p.exists() else Path.cwd() / config.RUNS_DIR / arg


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="Check invariants I1-I6 for one run")
    ap.add_argument("run", help="run id under runs/ or a path")
    ap.add_argument("--self-test", action="store_true", help="prove the checker flags known corruptions")
    ap.add_argument("--out", default=config.RESULTS_DIR)
    args = ap.parse_args(argv)
    run_dir = resolve_run(args.run)
    if args.self_test:
        ok, rows = self_test(run_dir)
        md = self_test_markdown(run_dir, rows)
        Path(args.out).mkdir(parents=True, exist_ok=True)
        (Path(args.out) / "checker_self_test.md").write_text(md, encoding="utf-8")
        print(md)
        return 0 if ok else 1
    run = RunData.load(run_dir)
    results = check_run(run)
    md = write_reports(run, results, Path(args.out))
    for r in results:
        print(f"{r.invariant:3} {r.side:5} {r.status:4}  {r.detail}")
    for side in SIDES:
        print("latency", latency(run, side))
    print(f"overall: {overall(results)}  ->  {md}")
    return 0 if overall(results) == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
