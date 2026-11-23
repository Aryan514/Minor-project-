# equipment/audit.py
# Global monotonic sequence counter + append-only JSONL audit writer.
# The audit log is the "oracle" of the consistency method: every state change, event and alarm
# gets a seq here, and the checker compares what each client received against these records.
# Serves N3 (seq oracle) and N1 (every state change is audited under the core lock).
"""Sequence-numbered audit log (runs/<run_id>/core_audit.jsonl)."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional, TextIO


@dataclass(frozen=True)
class AuditRecord:
    """One line of the audit log.

    Attributes:
        seq: global monotonic sequence number (starts at 1).
        ts_ns: wall-clock time in ns (time.time_ns()) when the record was created.
        kind: one of config.AuditKind values (as string).
        id: what the record is about (CEID, ALID, variable name, RCMD ...).
        value: the new value / payload.
        origin: who caused it (config.Origin value as string).
        extra: free-form details (reason, names, cause seq ...).
    """

    seq: int
    ts_ns: int
    kind: str
    id: Any
    value: Any
    origin: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialise as one JSON line (dict keys become strings, as JSON requires)."""
        return json.dumps(asdict(self), default=str)


class AuditLog:
    """Assigns sequence numbers and writes records to a JSONL file, flushing every line.

    The caller (EquipmentCore) holds its own lock while calling `append`, so seq order equals
    the order in which state changes were applied. An internal lock makes the log safe on its own too.
    """

    def __init__(self, path: Optional[Path] = None, keep_in_memory: bool = True) -> None:
        """Create the log.

        Args:
            path: JSONL file to append to; None keeps the log in memory only (unit tests).
            keep_in_memory: also keep every record in `self.records` (used by tests and the console).
        """
        self._lock = threading.Lock()
        self._next_seq = 1
        self._keep = keep_in_memory
        self.records: list[AuditRecord] = []
        self._file: Optional[TextIO] = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(path, "a", encoding="utf-8")  # noqa: SIM115 - closed in close()

    @property
    def last_seq(self) -> int:
        """The last seq handed out (0 if none yet)."""
        return self._next_seq - 1

    def append(
        self,
        kind: str,
        id_: Any,
        value: Any,
        origin: str,
        extra: Optional[dict[str, Any]] = None,
        seq: Optional[int] = None,
    ) -> AuditRecord:
        """Create, persist and return a new record.

        Args:
            seq: normally None (next seq is assigned). The core may pass a seq it reserved with
                `reserve()` so that an event can carry its own seq inside its payload (DVID 101).
        """
        with self._lock:
            if seq is None:
                seq = self._next_seq
                self._next_seq += 1
            elif seq != self._next_seq - 1:
                raise ValueError(f"reserved seq {seq} is not the most recently reserved one")
            record = AuditRecord(seq, time.time_ns(), str(kind), id_, value, str(origin), dict(extra or {}))
            if self._file is not None:
                self._file.write(record.to_json() + "\n")
                self._file.flush()
            if self._keep:
                self.records.append(record)
            return record

    def reserve(self) -> int:
        """Reserve the next seq; it must be used by the very next `append(..., seq=...)` call."""
        with self._lock:
            seq = self._next_seq
            self._next_seq += 1
            return seq

    def close(self) -> None:
        """Close the file (records stay in memory)."""
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None


class JsonlWriter:
    """Thread-safe append-only JSONL file, flushed after every line.

    Used for the adapters' send-side logs and the clients' receive-side logs (N3).
    """

    def __init__(self, path: Optional[Path]) -> None:
        """Open `path` for appending (None = discard everything)."""
        self._lock = threading.Lock()
        self._file: Optional[TextIO] = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(path, "a", encoding="utf-8")  # noqa: SIM115 - closed in close()

    def write(self, record: dict[str, Any]) -> None:
        """Append one record as a JSON line."""
        line = json.dumps(record, default=str)
        with self._lock:
            if self._file is not None:
                self._file.write(line + "\n")
                self._file.flush()

    def close(self) -> None:
        """Close the file."""
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None


def run_dir_for(run_id: str, base: Optional[Path] = None) -> Path:
    """Return runs/<run_id> (created if missing)."""
    from equipment.config import RUNS_DIR

    path = (base or Path.cwd()) / RUNS_DIR / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_run_id(base: Optional[Path] = None) -> Optional[str]:
    """The run id written by the last `equipment.main` start (runs/LATEST), if any."""
    from equipment.config import RUNS_DIR

    marker = (base or Path.cwd()) / RUNS_DIR / "LATEST"
    try:
        return marker.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None
