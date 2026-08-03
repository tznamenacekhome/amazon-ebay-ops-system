"""Read-only analyzer for sourcing matching feedback.

Summarizes normalized rule-family failures and evidence sources from
`sourcing_actions.raw_action_context`. The script does not call marketplaces,
does not rescore opportunities, and does not write production data.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any

from matching_feedback import matching_feedback_from_context
from sourcing_common import get_supabase_client


DEFAULT_REPORT = Path("docs/sourcing_matching_feedback_report.md")


def main() -> int:
    args = parse_args()
    rows = fetch_feedback_rows(args)
    summary = summarize_feedback_rows(rows, limit=args.limit)
    if args.csv:
        write_csv(args.csv, summary["examples"])
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(json_ready(summary), indent=2), encoding="utf-8")
    if args.report:
        write_report(args.report, summary)
    print("Matching feedback analysis")
    print("--------------------------")
    print(f"Actions scanned: {summary['actions_scanned']}")
    print(f"Actions with feedback: {summary['actions_with_feedback']}")
    print(f"Date range: {summary['date_range']['start'] or '--'} to {summary['date_range']['end'] or '--'}")
    print(f"Rule families: {dict(summary['rule_family_counts'])}")
    print(f"Evidence sources: {dict(summary['evidence_source_counts'])}")
    if args.report:
        print(f"Report: {args.report}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze stored matching feedback.")
    parser.add_argument("--since-days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--rule-family")
    parser.add_argument("--dismiss-reason")
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def fetch_feedback_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    supabase = get_supabase_client()
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=args.since_days)
    rows: list[dict[str, Any]] = []
    page_size = 1000
    start = 0
    while len(rows) < args.limit:
        end = min(start + page_size - 1, args.limit - 1)
        response = (
            supabase.table("sourcing_actions")
            .select("action_id,action_type,dismiss_reason,notes,raw_action_context,created_at")
            .gte("created_at", since.isoformat())
            .order("created_at", desc=True)
            .range(start, end)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    if args.dismiss_reason:
        rows = [row for row in rows if str(row.get("dismiss_reason") or "") == args.dismiss_reason]
    if args.rule_family:
        rows = [
            row
            for row in rows
            if args.rule_family in matching_feedback_from_context(row.get("raw_action_context")).get("failedRuleFamilies", [])
        ]
    return rows


def summarize_feedback_rows(rows: list[dict[str, Any]], *, limit: int = 1000) -> dict[str, Any]:
    rule_family_counts: Counter[str] = Counter()
    evidence_source_counts: Counter[str] = Counter()
    dismiss_reason_counts: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    dates: list[str] = []
    feedback_count = 0

    for row in rows[:limit]:
        context = row.get("raw_action_context")
        feedback = matching_feedback_from_context(context)
        has_feedback = bool(
            feedback["allAssumptionsCorrect"]
            or feedback["failedRuleFamilies"]
            or feedback["evidenceSources"]
            or feedback["legacyIncorrectRows"]
        )
        if not has_feedback:
            continue
        feedback_count += 1
        if row.get("created_at"):
            dates.append(str(row["created_at"]))
        if row.get("dismiss_reason"):
            dismiss_reason_counts[str(row["dismiss_reason"])] += 1
        for family in feedback["failedRuleFamilies"]:
            rule_family_counts[family] += 1
        for source in feedback["evidenceSources"]:
            evidence_source_counts[source] += 1
        if len(examples) < 50:
            examples.append(
                {
                    "action_id": row.get("action_id"),
                    "created_at": row.get("created_at"),
                    "action_type": row.get("action_type"),
                    "dismiss_reason": row.get("dismiss_reason"),
                    "all_assumptions_correct": feedback["allAssumptionsCorrect"],
                    "failed_rule_families": "; ".join(feedback["failedRuleFamilies"]),
                    "evidence_sources": "; ".join(feedback["evidenceSources"]),
                    "legacy_incorrect_rows": "; ".join(feedback["legacyIncorrectRows"]),
                    "note": feedback.get("note") or row.get("notes"),
                }
            )

    return {
        "actions_scanned": len(rows[:limit]),
        "actions_with_feedback": feedback_count,
        "date_range": {
            "start": min(dates) if dates else None,
            "end": max(dates) if dates else None,
        },
        "rule_family_counts": rule_family_counts,
        "evidence_source_counts": evidence_source_counts,
        "dismiss_reason_counts": dismiss_reason_counts,
        "examples": examples,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "action_id",
        "created_at",
        "action_type",
        "dismiss_reason",
        "all_assumptions_correct",
        "failed_rule_families",
        "evidence_sources",
        "legacy_incorrect_rows",
        "note",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    add = lines.append
    add("# Matching Feedback Report")
    add("")
    add(f"Generated: {dt.datetime.now(dt.UTC).isoformat()}")
    add("")
    add(f"Actions scanned: {summary['actions_scanned']}")
    add(f"Actions with feedback: {summary['actions_with_feedback']}")
    add(f"Date range: {summary['date_range']['start'] or '--'} to {summary['date_range']['end'] or '--'}")
    add("")
    add("## Rule Families")
    add("")
    markdown_counts(lines, summary["rule_family_counts"])
    add("")
    add("## Evidence Sources")
    add("")
    markdown_counts(lines, summary["evidence_source_counts"])
    add("")
    add("## Dismiss Reasons")
    add("")
    markdown_counts(lines, summary["dismiss_reason_counts"])
    add("")
    add("## Representative Examples")
    add("")
    markdown_examples(lines, summary["examples"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def markdown_counts(lines: list[str], counts: Counter[str]) -> None:
    lines.append("| Key | Count |")
    lines.append("| --- | --- |")
    if not counts:
        lines.append("| None | 0 |")
        return
    for key, count in counts.most_common():
        lines.append(f"| {clean_md(key)} | {count} |")


def markdown_examples(lines: list[str], rows: list[dict[str, Any]]) -> None:
    fields = ["created_at", "dismiss_reason", "failed_rule_families", "evidence_sources", "note"]
    lines.append("| " + " | ".join(fields) + " |")
    lines.append("| " + " | ".join("---" for _ in fields) + " |")
    if not rows:
        lines.append("| -- | -- | -- | -- | -- |")
        return
    for row in rows[:25]:
        lines.append("| " + " | ".join(clean_md(row.get(field)) for field in fields) + " |")


def clean_md(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def json_ready(value: Any) -> Any:
    if isinstance(value, Counter):
        return dict(value)
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
