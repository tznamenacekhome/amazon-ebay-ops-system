from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATIONS = ROOT / "integrations"
if str(INTEGRATIONS) not in sys.path:
    sys.path.insert(0, str(INTEGRATIONS))

import keepa_sync_products as keepa_sync  # noqa: E402


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def select(self, _columns):
        return self

    def range(self, start, end):
        self.start = start
        self.end = end
        return self

    def execute(self):
        return _Response(self.rows[getattr(self, "start", 0):getattr(self, "end", len(self.rows) - 1) + 1])


class _Supabase:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return _Query(self.tables.get(name, []))


def test_freshness_source_includes_every_wholesale_candidate(monkeypatch):
    monkeypatch.setattr(keepa_sync, "fetch_return_recovery_fba_asins", lambda _supabase: [])
    supabase = _Supabase({
        "purchase_items": [],
        "sourcing_opportunities": [],
        "amazon_skus": [],
        "amazon_sales_profitability": [],
        "manual_item_matches": [],
        "wholesale_amazon_candidates": [
            {"asin": "B000000001"},
            {"asin": "B000000002"},
            {"asin": "B000000001"},
        ],
    })

    asins, priorities = keepa_sync.collect_source_asins(supabase, source="freshness_24h")

    assert asins == ["B000000001", "B000000002"]
    assert priorities == {
        "B000000001": keepa_sync.SOURCE_PRIORITY_HIGH,
        "B000000002": keepa_sync.SOURCE_PRIORITY_HIGH,
    }


def test_catalog_cycle_continues_when_eligible_count_changes(monkeypatch):
    previous_cycle = {
        "cycle_started_at": "2026-07-28T17:30:23Z",
        "eligible_count": 6171,
        "remaining_after": 2,
        "remaining_asins_after": ["B001", "B002"],
        "cycle_tokens_used_after": 100,
        "cycle_token_tracked_asins_after": 20,
    }
    monkeypatch.setattr(
        keepa_sync,
        "fetch_latest_keepa_cycle_metadata",
        lambda _supabase: {"keepa_catalog_cycle": previous_cycle},
    )
    monkeypatch.setattr(
        keepa_sync,
        "fetch_latest_snapshot_by_asin",
        lambda _supabase, _asins: {},
    )

    state = keepa_sync.build_catalog_cycle_state(
        object(),
        ["B001", "B002", "B003"],
        priority_by_asin={"B003": keepa_sync.SOURCE_PRIORITY_HIGH},
        captured_at="2026-08-01T15:59:50Z",
    )

    assert state["cycle_id"] == "keepa-20260728-2cf5ecd8"
    assert state["cycle_started_at"] == "2026-07-28T17:30:23Z"
    assert state["eligible_count"] == 6172
    assert state["remaining_asins"] == ["B003", "B001", "B002"]
    assert state["cycle_tokens_used_before"] == 100
    assert state["cycle_token_tracked_asins_before"] == 20


def test_catalog_cycle_reprioritizes_unfinished_queue(monkeypatch):
    previous_cycle = {
        "cycle_started_at": "2026-07-28T17:30:23Z",
        "eligible_count": 3,
        "remaining_after": 3,
        "remaining_asins_after": ["B001", "B002", "B003"],
    }
    monkeypatch.setattr(
        keepa_sync,
        "fetch_latest_keepa_cycle_metadata",
        lambda _supabase: {"keepa_catalog_cycle": previous_cycle},
    )
    monkeypatch.setattr(
        keepa_sync,
        "fetch_latest_snapshot_by_asin",
        lambda _supabase, _asins: {},
    )

    state = keepa_sync.build_catalog_cycle_state(
        object(),
        ["B001", "B002", "B003"],
        priority_by_asin={"B003": keepa_sync.SOURCE_PRIORITY_HIGH},
        captured_at="2026-08-01T15:59:50Z",
    )

    assert state["remaining_asins"] == ["B003", "B001", "B002"]


def test_catalog_cycle_starts_new_cycle_after_previous_completes(monkeypatch):
    previous_cycle = {
        "cycle_started_at": "2026-07-28T17:30:23Z",
        "eligible_count": 6171,
        "remaining_after": 0,
        "remaining_asins_after": [],
        "cycle_tokens_used_after": 100,
        "cycle_token_tracked_asins_after": 20,
    }
    monkeypatch.setattr(
        keepa_sync,
        "fetch_latest_keepa_cycle_metadata",
        lambda _supabase: {"keepa_catalog_cycle": previous_cycle},
    )
    monkeypatch.setattr(
        keepa_sync,
        "fetch_latest_snapshot_by_asin",
        lambda _supabase, _asins: {},
    )

    state = keepa_sync.build_catalog_cycle_state(
        object(),
        ["B002", "B001"],
        priority_by_asin={"B001": keepa_sync.SOURCE_PRIORITY_MEDIUM},
        captured_at="2026-08-01T15:59:50Z",
    )

    assert state["cycle_id"] == "keepa-20260801-a190d6fe"
    assert state["cycle_started_at"] == "2026-08-01T15:59:50Z"
    assert state["eligible_count"] == 2
    assert state["remaining_asins"] == ["B001", "B002"]
    assert state["cycle_tokens_used_before"] == 0


def test_cycle_metadata_selector_prefers_original_unfinished_cycle():
    selected = keepa_sync.select_keepa_cycle_metadata(
        [
            {
                "started_at": "2026-08-04T00:59:54Z",
                "metadata": {
                    "keepa_catalog_cycle": {
                        "cycle_id": "keepa-20260802-c933d123",
                        "cycle_started_at": "2026-08-02T05:59:48Z",
                        "remaining_after": 4184,
                    }
                },
            },
            {
                "started_at": "2026-08-01T15:29:45Z",
                "metadata": {
                    "keepa_catalog_cycle": {
                        "cycle_id": "keepa-20260728-2cf5ecd8",
                        "cycle_started_at": "2026-07-28T17:30:23Z",
                        "remaining_after": 2161,
                    }
                },
            },
        ]
    )

    assert selected["keepa_catalog_cycle"]["cycle_id"] == "keepa-20260728-2cf5ecd8"


def test_cycle_metadata_selector_ignores_superseded_cycles_after_original_completes():
    selected = keepa_sync.select_keepa_cycle_metadata(
        [
            {
                "started_at": "2026-08-04T02:00:00Z",
                "metadata": {
                    "keepa_catalog_cycle": {
                        "cycle_id": "keepa-20260728-2cf5ecd8",
                        "cycle_started_at": "2026-07-28T17:30:23Z",
                        "remaining_after": 0,
                    }
                },
            },
            {
                "started_at": "2026-08-04T00:59:54Z",
                "metadata": {
                    "keepa_catalog_cycle": {
                        "cycle_id": "keepa-20260802-c933d123",
                        "cycle_started_at": "2026-08-02T05:59:48Z",
                        "remaining_after": 4184,
                    }
                },
            },
        ]
    )

    assert selected["keepa_catalog_cycle"]["cycle_id"] == "keepa-20260728-2cf5ecd8"
