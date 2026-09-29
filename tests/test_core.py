import io
import json
import logging
import unittest

from process_lifecycle_marker import LifecycleMarker, LifecycleRecord


class TestLifecycleMarkerStream(unittest.TestCase):
    def test_startup_and_shutdown_emit_paired_records(self):
        stream = io.StringIO()
        t = [1000.0]
        w = [1700000000.0]
        m = LifecycleMarker(
            stream=stream,
            clock=lambda: t[0],
            wall_clock=lambda: w[0],
            boot_id_source=lambda: "boot-abc",
        )

        up = m.startup()
        t[0] = 1005.0
        w[0] = 1700000005.0
        down = m.shutdown()

        lines = [json.loads(l) for l in stream.getvalue().splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["event"], "startup")
        self.assertEqual(lines[1]["event"], "shutdown")
        self.assertEqual(lines[0]["boot_id"], "boot-abc")
        self.assertEqual(lines[1]["boot_id"], "boot-abc")
        self.assertEqual(lines[0]["uptime_seconds"], 0.0)
        self.assertEqual(lines[1]["uptime_seconds"], 5.0)
        self.assertEqual(lines[0]["timestamp_unix"], 1700000000.0)
        self.assertEqual(lines[1]["timestamp_unix"], 1700000005.0)

        # Returned records match emitted lines.
        self.assertIsInstance(up, LifecycleRecord)
        self.assertIsInstance(down, LifecycleRecord)
        self.assertEqual(up.event, "startup")
        self.assertEqual(down.event, "shutdown")

    def test_pid_is_captured(self):
        import os

        stream = io.StringIO()
        m = LifecycleMarker(
            stream=stream,
            clock=lambda: 0.0,
            wall_clock=lambda: 0.0,
            boot_id_source=lambda: "x",
        )
        rec = m.startup()
        self.assertEqual(rec.pid, os.getpid())

    def test_double_startup_raises(self):
        m = LifecycleMarker(
            stream=io.StringIO(),
            clock=lambda: 0.0,
            wall_clock=lambda: 0.0,
            boot_id_source=lambda: "x",
        )
        m.startup()
        with self.assertRaises(RuntimeError):
            m.startup()

    def test_shutdown_before_startup_raises(self):
        m = LifecycleMarker(
            stream=io.StringIO(),
            clock=lambda: 0.0,
            wall_clock=lambda: 0.0,
            boot_id_source=lambda: "x",
        )
        with self.assertRaises(RuntimeError):
            m.shutdown()

    def test_requires_logger_or_stream(self):
        with self.assertRaises(ValueError):
            LifecycleMarker()

    def test_rejects_both_logger_and_stream(self):
        logger = logging.getLogger("test_both")
        with self.assertRaises(ValueError):
            LifecycleMarker(logger=logger, stream=io.StringIO())

    def test_missing_boot_id_yields_empty_string(self):
        stream = io.StringIO()
        m = LifecycleMarker(
            stream=stream,
            clock=lambda: 0.0,
            wall_clock=lambda: 0.0,
            boot_id_source=lambda: "",
        )
        rec = m.startup()
        self.assertEqual(rec.boot_id, "")
        parsed = json.loads(stream.getvalue().splitlines()[0])
        self.assertEqual(parsed["boot_id"], "")

    def test_logger_emits_json_line_at_info(self):
        logger = logging.getLogger("test_logger_emit")
        logger.setLevel(logging.INFO)
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)

        m = LifecycleMarker(
            logger=logger,
            clock=lambda: 10.0,
            wall_clock=lambda: 1700000010.0,
            boot_id_source=lambda: "bid",
        )
        m.startup()

        raw = buf.getvalue().strip()
        parsed = json.loads(raw)
        self.assertEqual(parsed["event"], "startup")
        self.assertEqual(parsed["boot_id"], "bid")

    def test_uptime_uses_monotonic_clock_delta(self):
        times = [500.0, 500.0, 530.0]
        idx = [0]

        def clock():
            v = times[idx[0]]
            idx[0] = min(idx[0] + 1, len(times) - 1)
            return v

        stream = io.StringIO()
        m = LifecycleMarker(
            stream=stream,
            clock=clock,
            wall_clock=lambda: 0.0,
            boot_id_source=lambda: "z",
        )
        up = m.startup()
        down = m.shutdown()
        self.assertEqual(up.uptime_seconds, 0.0)
        self.assertEqual(down.uptime_seconds, 30.0)

    def test_to_dict_round_trips(self):
        rec = LifecycleRecord(
            event="startup",
            boot_id="b",
            pid=123,
            uptime_seconds=1.5,
            timestamp_unix=99.0,
        )
        d = rec.to_dict()
        self.assertEqual(
            d,
            {
                "event": "startup",
                "boot_id": "b",
                "pid": 123,
                "uptime_seconds": 1.5,
                "timestamp_unix": 99.0,
            },
        )

    def test_record_is_frozen(self):
        rec = LifecycleRecord("startup", "b", 1, 0.0, 0.0)
        with self.assertRaises(Exception):
            rec.event = "shutdown"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
