# Process Lifecycle Marker

Emits paired startup/shutdown log records tagged with the machine boot_id, the process pid, and process uptime, so downstream log queries can bound a session by searching for the matching marker pair.

## Usage

```python
import logging
from process_lifecycle_marker import LifecycleMarker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("myapp")

marker = LifecycleMarker(logger=logger)
marker.startup()
# ... application work ...
marker.shutdown()
```

Or write to a stream instead of a logger:

```python
import sys
from process_lifecycle_marker import LifecycleMarker

marker = LifecycleMarker(stream=sys.stdout)
marker.startup()
marker.shutdown()
```

Each emit writes one JSON line with keys `event`, `boot_id`, `pid`, `uptime_seconds`, and `timestamp_unix`. `startup()` and `shutdown()` each return the `LifecycleRecord` they emitted.

## Why

The problem: when grepping logs for a long-running process, there is no reliable boundary telling you where one run ended and the next began. Crash restarts, deploys, and manual restarts all blur together. This library inserts explicit `"event": "startup"` and `"event": "shutdown"` lines carrying the boot_id (so you can tell reboots apart from in-place restarts) and uptime (so you can sanity-check that the shutdown line came from the same run as the startup).

Trade-off: the library writes exactly two lines per run and nothing in between. It is not a general structured-logging framework. If you want per-request tracing, use something else; this is only for process-level boundaries.

## Edge cases

- `boot_id` is read from `/proc/sys/kernel/random/boot_id`. On systems where that file is absent or unreadable (containers without the proc mount, non-Linux OSes), `boot_id` is an empty string rather than a fabricated value. A fake uuid would be indistinguishable from a real one in queries and would defeat the purpose.
- `startup()` may be called exactly once. Calling it twice raises `RuntimeError`. Calling `shutdown()` before `startup()` raises `RuntimeError`.
- You must pass exactly one of `logger` or `stream`; passing both or neither raises `ValueError`.
- Uptime uses `time.monotonic` by default so it is immune to wall-clock adjustments. Both the monotonic clock and the wall clock are injectable via constructor arguments for testing.
