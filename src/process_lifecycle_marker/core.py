from __future__ import annotations

import io
import logging
import os
import time
from dataclasses import dataclass
from typing import Callable, Optional, TextIO, Union


__all__ = ["LifecycleMarker", "LifecycleRecord"]


# A "clock" is any zero-arg callable returning a monotonic-ish float in
# seconds. Defaulting to time.monotonic rather than time.time keeps uptime
# measurements immune to wall-clock adjustments (NTP, manual changes), which
# is the right default for measuring elapsed durations. Tests inject a fake.
Clock = Callable[[], float]


@dataclass(frozen=True)
class LifecycleRecord:
    """A single lifecycle marker event.

    Fields are deliberately flat primitives so the record serialises cleanly
    into JSON or a log line without custom adapters.
    """

    event: str
    boot_id: str
    pid: int
    uptime_seconds: float
    timestamp_unix: float

    def to_dict(self) -> dict:
        return {
            "event": self.event,
            "boot_id": self.boot_id,
            "pid": self.pid,
            "uptime_seconds": self.uptime_seconds,
            "timestamp_unix": self.timestamp_unix,
        }


class LifecycleMarker:
    """Emit startup and shutdown log records tagged with boot_id and uptime.

    The marker writes two structured lines to a logger or stream: one on
    startup, one on shutdown. Each carries the machine boot_id (when
    readable), the process pid, and the process uptime at emit time. The
    intent is that log queries can later bound a session by searching for
    the matching startup/shutdown pair.

    Parameters
    ----------
    logger:
        A logging.Logger. If supplied, records are emitted at INFO via
        logger.info. Mutually exclusive with stream.
    stream:
        A text stream. If supplied, records are written as one JSON line
        each. Mutually exclusive with logger.
    clock:
        Zero-arg callable returning a float, used for uptime. Default
        time.monotonic. Inject a fake in tests.
    wall_clock:
        Zero-arg callable returning a unix timestamp float. Default
        time.time. Inject a fake in tests.
    boot_id_source:
        Callable returning the boot id string, or empty string if
        unavailable. Default reads /proc/sys/kernel/random/boot_id and
        falls back to "" on any error. Injected in tests so the suite
        never touches the real filesystem.
    """

    def __init__(
        self,
        *,
        logger: Optional[logging.Logger] = None,
        stream: Optional[TextIO] = None,
        clock: Clock = time.monotonic,
        wall_clock: Clock = time.time,
        boot_id_source: Optional[Callable[[], str]] = None,
    ) -> None:
        if logger is None and stream is None:
            raise ValueError("LifecycleMarker requires either logger or stream")
        if logger is not None and stream is not None:
            raise ValueError("LifecycleMarker accepts logger or stream, not both")

        self._logger = logger
        self._stream = stream
        self._clock = clock
        self._wall_clock = wall_clock
        self._boot_id_source = boot_id_source or _default_boot_id
        self._start: Optional[float] = None
        self._boot_id: str = ""
        self._pid: int = os.getpid()
        self._started = False

    def startup(self) -> LifecycleRecord:
        """Emit the startup marker. Raises RuntimeError if called twice."""
        if self._started:
            raise RuntimeError("startup() already called")
        self._start = self._clock()
        self._boot_id = self._boot_id_source()
        self._started = True
        record = self._build_record("startup")
        self._emit(record)
        return record

    def shutdown(self) -> LifecycleRecord:
        """Emit the shutdown marker. Raises RuntimeError if startup() was not called."""
        if not self._started or self._start is None:
            raise RuntimeError("shutdown() called before startup()")
        record = self._build_record("shutdown")
        self._emit(record)
        return record

    def _build_record(self, event: str) -> LifecycleRecord:
        now = self._clock()
        uptime = now - self._start if self._start is not None else 0.0
        return LifecycleRecord(
            event=event,
            boot_id=self._boot_id,
            pid=self._pid,
            uptime_seconds=uptime,
            timestamp_unix=self._wall_clock(),
        )

    def _emit(self, record: LifecycleRecord) -> None:
        import json

        line = json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True)
        if self._logger is not None:
            self._logger.info(line)
        elif self._stream is not None:
            self._stream.write(line + "\n")
            self._stream.flush()


def _default_boot_id() -> str:
    """Read /proc/sys/kernel/random/boot_id, returning '' on any failure.

    We swallow all errors because the boot_id is a best-effort enrichment:
    its absence must not break logging. We deliberately do not fall back to
    a random uuid, because a fabricated id would be indistinguishable from
    a real one in log queries and would defeat the purpose of session
    bounding.
    """
    try:
        with open("/proc/sys/kernel/random/boot_id", "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""
