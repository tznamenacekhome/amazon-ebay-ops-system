import sys
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
from inventorylab_active_inventory_backfill import parse_args


class HistoricalMetadataDefaults(TestCase):
    def test_zero_on_hand_history_is_kept_by_default(self):
        with patch.object(sys, "argv", ["importer"]):
            self.assertTrue(parse_args().include_inactive)

    def test_explicit_active_only_and_legacy_flag(self):
        with patch.object(sys, "argv", ["importer", "--active-only"]):
            self.assertFalse(parse_args().include_inactive)
        with patch.object(sys, "argv", ["importer", "--include-inactive"]):
            self.assertTrue(parse_args().include_inactive)


if __name__ == "__main__":
    main()
