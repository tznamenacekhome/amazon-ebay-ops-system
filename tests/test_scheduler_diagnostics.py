import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run_all_syncs import run_streamed_process
from integrations import scheduler_diagnostics as diagnostics
import httpx


class StreamingTests(unittest.TestCase):
    def test_output_arrives_before_child_finishes_and_survives_abrupt_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / "release"
            code = ("import os,time,pathlib; print('Rows inserted: 7',flush=True); "
                    f"p=pathlib.Path({str(release)!r})\n"
                    "while not p.exists(): time.sleep(.02)\nos._exit(9)")
            observed = threading.Event()
            results = []
            def capture(*args, **kwargs):
                if args and "Rows inserted: 7" in str(args[0]):
                    observed.set()
            with patch("builtins.print", side_effect=capture):
                worker = threading.Thread(target=lambda: results.append(run_streamed_process([sys.executable, "-u", "-c", code], 10)))
                worker.start()
                try:
                    self.assertTrue(observed.wait(5), "Child output stayed buffered")
                    self.assertTrue(worker.is_alive())
                finally:
                    release.touch()
                    worker.join(10)
            result, metrics, size = results[0]
            self.assertEqual(result.returncode, 9)
            self.assertEqual(metrics["rows_inserted"], 7)
            self.assertGreater(size, 0)

    def test_timeout_retains_metrics_and_kills_process(self):
        with patch("builtins.print"), self.assertRaises(subprocess.TimeoutExpired) as caught:
            run_streamed_process([sys.executable, "-u", "-c", "import time; print('Rows updated: 4',flush=True); time.sleep(30)"], 1)
        self.assertEqual(caught.exception.metrics["rows_updated"], 4)
        self.assertGreater(caught.exception.log_bytes, 0)


class DiagnosticsTests(unittest.TestCase):
    def test_fargate_v1_memory_counter_fallback(self):
        def read(path):
            values = {"/sys/fs/cgroup/memory/memory.usage_in_bytes": "12345",
                      "/sys/fs/cgroup/memory/memory.limit_in_bytes": "2097152"}
            if str(path).replace("\\", "/") in values:
                return values[str(path).replace("\\", "/")]
            raise FileNotFoundError()
        with patch.object(Path, "read_text", read):
            values = diagnostics.memory()
        self.assertEqual(values["cgroup_memory_current"], "12345")
        self.assertEqual(values["cgroup_memory_max"], "2097152")

    def test_request_trace_omits_headers_query_values_and_bodies(self):
        events = []
        original = httpx.Client.send
        diagnostics._installed = False
        try:
            with patch.object(diagnostics, "emit", side_effect=lambda event, **values: events.append({"event": event, **values})), \
                    patch.object(diagnostics.threading, "Thread"), patch.object(diagnostics.atexit, "register"):
                diagnostics.install()
                transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"secret_response": "private"}))
                with httpx.Client(transport=transport) as client:
                    response = client.post("https://froeucjkcepuhgwisped.supabase.co/rest/v1/sourcing_actions?asin=eq.PRIVATEASIN&limit=100",
                                           headers={"Authorization": "Bearer SECRET"}, json={"private_note": "sensitive"})
                self.assertEqual(response.json(), {"secret_response": "private"})
        finally:
            httpx.Client.send = original
            diagnostics._installed = False
        serialized = json.dumps(events)
        for forbidden in ("PRIVATEASIN", "SECRET", "private_note", "sensitive", "secret_response"):
            self.assertNotIn(forbidden, serialized)
        end = next(event for event in events if event["event"] == "db_request_end")
        self.assertEqual(end["status"], 200)
        self.assertEqual(end["limit"], 100)
        self.assertGreater(end["response_bytes"], 0)

    def test_pressure_parser_keeps_only_allowed_numeric_metrics(self):
        values = diagnostics.parse_pressure('node_memory_MemAvailable_bytes 123\nsecret_metric{label="secret"} 456\nnode_filesystem_avail_bytes{mountpoint="/data"} 789\n')
        self.assertEqual(values, {"node_memory_MemAvailable_bytes": 123, "node_filesystem_avail_bytes": 789})
