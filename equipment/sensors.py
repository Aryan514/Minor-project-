# equipment/sensors.py
# Temperature sources for the chamber: a seedable simulation (default, no hardware needed) and an
# optional ESP32 + DS18B20 over serial. Both expose read() and set_heater(); SamplingThread feeds
# readings into the core every sample period and survives sensor faults.
# Supports N1/N3 by giving every run a reproducible physical process (fixed seed).
"""Sensors: SimulatedChamber, SerialESP32 and the sampling thread (CLAUDE.md section 5)."""

from __future__ import annotations

import json
import logging
import random
import threading
import time
from typing import Callable, Optional, Protocol

from equipment import config

_log = logging.getLogger(__name__)


class SensorFault(RuntimeError):
    """Raised by read() when no valid reading is available."""


class Sensor(Protocol):
    """Common interface of every temperature source."""

    def read(self) -> float:
        """Return the current chamber temperature in degC (may raise SensorFault)."""
        ...

    def set_heater(self, on: bool) -> None:
        """Switch the heater (or the ESP32 LED standing in for it)."""
        ...


class SimulatedChamber:
    """Deterministic first-order chamber model.

    Each read() advances model time by one sample period (not wall clock), so a given seed always
    produces the same temperature sequence. Heater on: rise toward 60 degC at 0.8 degC/s;
    heater off: fall toward ambient at 0.5 degC/s; uniform noise +-0.05 on the reading.
    """

    def __init__(
        self,
        seed: int = config.SIM_DEFAULT_SEED,
        sample_period_s: float = config.SIM_SAMPLE_PERIOD_S,
        initial_temp: float = config.SIM_AMBIENT_C,
    ) -> None:
        """Create the model with a seeded noise generator."""
        self._rng = random.Random(seed)
        self._dt = sample_period_s
        self._temp = initial_temp
        self._heater = False
        self._lock = threading.Lock()

    @property
    def heater_on(self) -> bool:
        """Current heater state."""
        return self._heater

    def set_heater(self, on: bool) -> None:
        """Switch the simulated heater."""
        with self._lock:
            self._heater = bool(on)

    def read(self) -> float:
        """Advance the model by one sample period and return a noisy reading."""
        with self._lock:
            if self._heater:
                step = config.SIM_HEAT_RATE_C_PER_S * self._dt
                self._temp = min(self._temp + step, config.SIM_HEATER_TARGET_C)
            else:
                step = config.SIM_COOL_RATE_C_PER_S * self._dt
                self._temp = max(self._temp - step, config.SIM_AMBIENT_C)
            noise = self._rng.uniform(-config.SIM_NOISE_C, config.SIM_NOISE_C)
            return round(self._temp + noise, 3)


class SerialESP32:
    """ESP32 + DS18B20 over USB serial (optional; CLAUDE.md section 5 and 15).

    A reader thread parses lines like {"seq":n,"t_ms":ms,"temp_c":x}. If the port disappears the
    sensor is marked faulty and read() raises SensorFault; the core keeps running.
    """

    def __init__(self, port: str, baud: int = config.SERIAL_BAUD) -> None:
        """Open the serial port and start the reader thread."""
        import serial  # pyserial; imported lazily so the sim mode never needs a port

        self._serial = serial.Serial(port, baud, timeout=1.0)
        self._latest: Optional[float] = None
        self.fault: Optional[str] = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._reader, name="esp32-reader", daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        while not self._stop.is_set():
            try:
                line = self._serial.readline().decode("utf-8", errors="replace").strip()
            except Exception as exc:  # noqa: BLE001 - port unplugged etc.
                self.fault = f"serial error: {exc}"
                _log.error("ESP32 sensor fault: %s", exc)
                return
            if not line:
                continue
            try:
                self._latest = float(json.loads(line)["temp_c"])
                self.fault = None
            except (ValueError, KeyError, TypeError):
                _log.debug("ignoring serial line %r", line)

    def read(self) -> float:
        """Return the latest temperature received from the ESP32."""
        if self.fault is not None:
            raise SensorFault(self.fault)
        if self._latest is None:
            raise SensorFault("no reading received yet")
        return self._latest

    def set_heater(self, on: bool) -> None:
        """Send H1/H0 (the ESP32 toggles its LED)."""
        try:
            self._serial.write(config.SERIAL_HEATER_ON if on else config.SERIAL_HEATER_OFF)
        except Exception as exc:  # noqa: BLE001
            self.fault = f"serial write error: {exc}"
            _log.error("ESP32 heater write failed: %s", exc)

    def close(self) -> None:
        """Stop the reader and close the port."""
        self._stop.set()
        try:
            self._serial.close()
        except Exception:  # noqa: BLE001
            pass


class SamplingThread:
    """Calls sensor.read() every period and hands the value to `on_sample` (the core)."""

    def __init__(
        self,
        sensor: Sensor,
        on_sample: Callable[[float], None],
        period_s: float = config.SIM_SAMPLE_PERIOD_S,
    ) -> None:
        """Prepare the thread (call start())."""
        self._sensor = sensor
        self._on_sample = on_sample
        self._period = period_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sampler", daemon=True)

    def start(self) -> None:
        """Start sampling."""
        self._thread.start()

    def _run(self) -> None:
        next_t = time.monotonic()
        while not self._stop.is_set():
            try:
                self._on_sample(self._sensor.read())
            except SensorFault as exc:
                _log.warning("sensor fault: %s", exc)
            except Exception:  # noqa: BLE001 - keep sampling no matter what
                _log.exception("sample handling failed")
            next_t += self._period
            self._stop.wait(max(0.0, next_t - time.monotonic()))

    def stop(self) -> None:
        """Stop sampling and wait for the thread."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(2.0)
