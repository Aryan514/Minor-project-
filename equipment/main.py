# equipment/main.py
# Entry point: python -m equipment.main [--sensor sim|serial] [--port COM3] [--seed 42] [--run-id X]
# Wires ONE core (audit + dispatcher + sensor) to its doors (OPC UA server, GEM equipment) and the
# operator console/control socket, then runs until `quit` or Ctrl+C.
# Serves N1 (one core serving both protocols at the same time).
"""Start the simulated dual-interface equipment."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Any, Optional

from equipment import config
from equipment.audit import AuditLog, run_dir_for
from equipment.console import ControlSocketServer, OperatorConsole
from equipment.core import EquipmentCore
from equipment.dispatcher import Dispatcher
from equipment.opcua_adapter import OpcUaAdapter
from equipment.sensors import SamplingThread, SerialESP32, SimulatedChamber


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Command-line options."""
    p = argparse.ArgumentParser(description="Dual-interface (SECS/GEM + OPC UA) simulated equipment")
    p.add_argument("--sensor", choices=["sim", "serial"], default="sim")
    p.add_argument("--port", default="COM3", help="serial port for --sensor serial")
    p.add_argument("--seed", type=int, default=config.SIM_DEFAULT_SEED, help="simulation seed")
    p.add_argument("--run-id", default=None, help="log folder name under runs/ (default: timestamp)")
    p.add_argument("--no-console", action="store_true", help="no stdin console (harness use)")
    p.add_argument("--no-gem", action="store_true", help="do not start the GEM door")
    p.add_argument("--no-ua", action="store_true", help="do not start the OPC UA door")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def setup_logging(run_dir: Path, level: str) -> None:
    """Log to runs/<id>/equipment.log and to stderr (warnings only for the chatty libraries)."""
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    handlers: list[logging.Handler] = [logging.FileHandler(run_dir / "equipment.log", encoding="utf-8"),
                                       logging.StreamHandler(sys.stderr)]
    logging.basicConfig(level=level.upper(), format=fmt, handlers=handlers)
    for noisy in ("asyncua", "secsgem", "communication"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def run(args: argparse.Namespace) -> int:
    """Build everything, serve until quit, shut down cleanly."""
    run_id = args.run_id or time.strftime("%Y%m%d-%H%M%S")
    run_dir = run_dir_for(run_id)
    (run_dir.parent / "LATEST").write_text(run_id, encoding="utf-8")
    setup_logging(run_dir, args.log_level)
    log = logging.getLogger("equipment.main")

    sensor: Any = SimulatedChamber(seed=args.seed) if args.sensor == "sim" else SerialESP32(args.port)
    audit = AuditLog(run_dir / config.CORE_AUDIT_FILE, keep_in_memory=False)
    dispatcher = Dispatcher()
    core = EquipmentCore(audit, dispatcher, sensor)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def request_stop() -> None:
        loop.call_soon_threadsafe(stop_event.set)

    console = OperatorConsole(core, on_quit=request_stop)
    control: Optional[ControlSocketServer] = None
    ua_door: Optional[OpcUaAdapter] = None
    gem_door: Any = None
    sampler: Optional[SamplingThread] = None
    # Everything after this point is cleaned up in `finally`, also when startup fails half-way
    # (e.g. a port is still in use), so no port is ever left open.
    try:
        control = ControlSocketServer(console)
        control.start_thread()
        if not args.no_ua:
            ua_door = OpcUaAdapter(core, dispatcher, run_dir)
            await ua_door.start()
        if not args.no_gem:
            from equipment.gem_adapter import GemAdapter  # imported here so --no-gem never touches secsgem

            gem_door = GemAdapter(core, dispatcher, run_dir)
            gem_door.start()

        sampler = SamplingThread(sensor, core.on_sample)
        sampler.start()
        if not args.no_console:
            console.start_stdin_thread()
        try:
            loop.add_signal_handler(signal.SIGINT, request_stop)
        except (NotImplementedError, RuntimeError):
            pass  # Windows: Ctrl+C raises KeyboardInterrupt in asyncio.run instead

        log.info("equipment running: run_id=%s, OPC UA %s, HSMS port %s, control %s:%s",
                 run_id, None if args.no_ua else config.OPCUA_ENDPOINT, None if args.no_gem else config.HSMS_PORT,
                 config.CONTROL_HOST, config.CONTROL_PORT)
        print(f"READY run_id={run_id}", flush=True)
        await stop_event.wait()
    finally:
        log.info("shutting down")
        if sampler is not None:
            sampler.stop()
        dispatcher.wait_idle(3.0)  # deliver (and send-log) what is already queued before closing the doors
        if gem_door is not None:
            gem_door.stop()
        if ua_door is not None:
            await ua_door.stop()
        dispatcher.stop()
        if control is not None:
            control.shutdown()
            control.server_close()
        audit.close()
        log.info("stopped")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """Synchronous entry point."""
    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
