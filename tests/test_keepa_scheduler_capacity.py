from __future__ import annotations

import unittest

from run_all_syncs import jobs_for_group


class KeepaSchedulerCapacityTests(unittest.TestCase):
    def test_priority_job_uses_expanded_subscription_capacity(self) -> None:
        jobs = jobs_for_group("keepa-catalog-priority")
        self.assertEqual(len(jobs), 1)
        command = jobs[0].command()

        self.assertEqual(command[command.index("--limit") + 1], "100")
        self.assertEqual(
            command[command.index("--estimated-tokens-per-asin") + 1],
            "10",
        )
        self.assertEqual(
            command[command.index("--weekend-token-reserve") + 1],
            "150",
        )


if __name__ == "__main__":
    unittest.main()
