# equipment/wire_log.py
# Writes every HSMS message that secsgem sends or receives to a JSONL "wire log" in SML text form. secsgem already
# reports each message to the standard logger named "communication"; this handler only records those reports, so
# no adapter code changes. Used by equipment.main (equipment side) and clients.gem_host (host side).
# Serves N3 (shows the real SECS-II traffic next to the audit oracle) and the panel's wire view.
"""JSONL wire log for secsgem's "communication" logger."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from equipment.audit import JsonlWriter

SECSGEM_COMM_LOGGER = "communication"  # secsgem/common/protocol.py: logging.getLogger("communication")


class SecsWireHandler(logging.Handler):
    """Turns secsgem's "> msg\\nSML" / "< msg\\nSML" log records into JSONL wire records."""

    def __init__(self, path: Path, side: str) -> None:
        """`side` is "equipment" or "host" (whose point of view "out"/"in" refers to)."""
        super().__init__(level=logging.INFO)
        self._writer = JsonlWriter(path)
        self._side = side

    def emit(self, record: logging.LogRecord) -> None:
        """Record one message; never raise into secsgem."""
        try:
            fmt = str(record.msg)
            args: Any = record.args if isinstance(record.args, tuple) else ()
            msg = args[0] if args else None
            header = getattr(msg, "header", None)
            body = str(args[1]) if len(args) > 1 else ""
            stype = getattr(getattr(header, "s_type", None), "value", None)
            rec = {
                "ts_ns": time.time_ns(),
                "side": self._side,
                "dir": "out" if fmt.startswith(">") else "in",
                "stream": getattr(header, "stream", None),
                "function": getattr(header, "function", None),
                "wbit": bool(getattr(header, "require_response", False)),
                "stype": stype,
                "system": getattr(header, "system", None),
                # data messages: SML body; control messages (select, linktest, separate): the SType text
                "sml": body.strip(),
            }
            self._writer.write(rec)
        except Exception:  # noqa: BLE001 - logging must never break the protocol stack
            self.handleError(record)

    def close(self) -> None:
        """Close the file."""
        self._writer.close()
        super().close()


def attach_secs_wire_log(path: Path, side: str) -> SecsWireHandler:
    """Attach the handler to secsgem's communication logger (INFO, not propagated to other logs)."""
    handler = SecsWireHandler(path, side)
    logger = logging.getLogger(SECSGEM_COMM_LOGGER)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    return handler
