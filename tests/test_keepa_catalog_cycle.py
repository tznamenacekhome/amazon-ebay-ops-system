from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATIONS = ROOT / "integrations"
if str(INTEGRATIONS) not in sys.path:
    sys.path.insert(0, str(INTEGRATIONS))

import keepa_sync_products as keepa_sync  # noqa: E402


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

    state = keepa_sync.build_catalog_cycle_state(
        object(),
        ["B001", "B002", "B003"],
        priority_by_asin={"B003": keepa_sync.SOURCE_PRIORITY_HIGH},
        captured_at="2026-08-01T15:59:50Z",
    )

    assert state["cycle_id"] == "keepa-20260728-2cf5ecd8"
    assert state["cycle_started_at"] == "2026-07-28T17:30:23Z"
    assert state["eligible_count"] == 6171
    assert state["remaining_asins"] == ["B001", "B002"]
    assert state["cycle_tokens_used_before"] == 100
    assert state["cycle_token_tracked_asins_before"] == 20


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
