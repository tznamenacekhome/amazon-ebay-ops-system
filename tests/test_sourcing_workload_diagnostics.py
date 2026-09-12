import json
import unittest
from unittest.mock import MagicMock, patch

from integrations import sourcing_workload_diagnostics as diagnostics


def row(**values):
    return {"userid": "1", "dbid": "2", "toplevel": True, "query_id": "3",
            "stats_since": "start", "stats_reset": "reset", "collector": False,
            **dict.fromkeys(diagnostics.COUNTERS, 0), **values}


class WorkloadTests(unittest.TestCase):
    def test_deltas_keep_spills_as_well_as_time_and_exclude_collector(self):
        before = [row(query_id=str(i)) for i in range(22)]
        after = [row(query_id=str(i), total_exec_time=i, calls=1) for i in range(22)]
        after[0]["temp_blks_written"] = 100
        after[-1]["collector"] = True
        result = diagnostics.statement_deltas(before, after)
        self.assertEqual(result["changed_statements"], 21)
        self.assertTrue(any(r["query_id"] == "0" for r in result["top_deltas"]))
        self.assertFalse(any(r["query_id"] == "21" for r in result["top_deltas"]))

    def test_reset_eviction_and_first_sample_are_baselines_not_fake_deltas(self):
        before = [row(calls=4)]
        for after in ([row(calls=5, stats_reset="new")],
                      [row(calls=5, stats_since="new")], [row(calls=1)]):
            result = diagnostics.statement_deltas(before, after)
            self.assertEqual(result["new_baselines"], 1)
            self.assertEqual(result["top_deltas"], [])
        self.assertEqual(diagnostics.statement_deltas([], before)["top_deltas"], [])

    def test_sample_reports_truncation_and_interval(self):
        sampler = diagnostics.WorkloadSampler(MagicMock())
        with patch.object(sampler, "query", side_effect=[[{"sampled_at": "now"}], [row()] * 2001]), \
                patch.object(diagnostics, "emit") as emit:
            sampler.sample(statements=True)
        event = emit.call_args_list[-1].kwargs
        self.assertTrue(event["truncated"])
        self.assertIsNone(event["interval_seconds"])
        self.assertEqual(len(sampler.previous), 2000)

    def test_only_readonly_endpoint_is_used_and_response_is_capped(self):
        session = MagicMock()
        response = session.post.return_value.__enter__.return_value
        response.iter_content.return_value = iter([b"x" * 1_000_001] * 2)
        with self.assertRaises(ValueError):
            diagnostics.WorkloadSampler(session).query(diagnostics.ACTIVITY_SQL)
        args, kwargs = session.post.call_args
        self.assertTrue(args[0].endswith("/database/query/read-only"))
        self.assertEqual(kwargs["timeout"], 8)

    def test_failure_backoff_does_not_log_exception_content(self):
        with patch.dict(diagnostics.os.environ, {"SUPABASE_URL": diagnostics.PROJECT_URL,
                                               "SUPABASE_ACCESS_TOKEN": "secret"}), \
                patch.object(diagnostics.WorkloadSampler, "sample", side_effect=RuntimeError("private SQL secret")), \
                patch.object(diagnostics, "emit") as emit, \
                patch.object(diagnostics.time, "sleep", side_effect=KeyboardInterrupt) as sleep:
            with self.assertRaises(KeyboardInterrupt):
                diagnostics.workload_loop()
        sleep.assert_called_once_with(60)
        self.assertNotIn("secret", str(emit.call_args_list))
        self.assertNotIn("private SQL", str(emit.call_args_list))

    def test_unexpected_project_never_queries(self):
        with patch.dict(diagnostics.os.environ, {"SUPABASE_URL": "https://other.supabase.co",
                                               "SUPABASE_ACCESS_TOKEN": "secret"}), \
                patch.object(diagnostics.requests, "Session") as session, \
                patch.object(diagnostics, "emit"):
            diagnostics.workload_loop()
        session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
