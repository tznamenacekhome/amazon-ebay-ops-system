from __future__ import annotations

import unittest

from run_all_syncs import jobs_for_group


class KeepaSchedulerCapacityTests(unittest.TestCase):
    def test_priority_job_uses_expanded_subscription_capacity(self) -> None:
        jobs = jobs_for_group("keepa-catalog-priority")
        keepa_jobs=[job for job in jobs if 'catalog_priority' in job.command()]
        self.assertEqual(len(keepa_jobs), 1)
        command = keepa_jobs[0].command()

        self.assertEqual(command[command.index("--limit") + 1], "100")
        self.assertEqual(
            command[command.index("--estimated-tokens-per-asin") + 1],
            "10",
        )
        self.assertEqual(
            command[command.index("--weekend-token-reserve") + 1],
            "150",
        )

    def test_checkpoint_recovery_reuses_existing_wakes_without_discovery(self):
        for group in ('keepa-catalog-priority','sourcing-catalog'):
            jobs=jobs_for_group(group)
            recoveries=[job for job in jobs if 'integrations/import_flipmine.py' in job.command()]
            self.assertEqual(len(recoveries),1)
            self.assertIn('--resume-due',recoveries[0].command())
            self.assertNotIn('--run-id',recoveries[0].command())
            self.assertFalse(recoveries[0].blocking)
            self.assertEqual(recoveries[0].command()[-2:],['--max-seconds','900'])


if __name__ == "__main__":
    unittest.main()
