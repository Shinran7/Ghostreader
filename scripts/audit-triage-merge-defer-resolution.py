#!/usr/bin/env python3
"""Merge defer wave results back into triage ledger."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def normalize_bucket(b: str) -> str:
    if b in ("fix", "reporting", "wontfix", "defer"):
        return b
    return "reporting"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dir",
        default="",
        help="Triage dir under .tmp/audit-triage",
    )
    parser.add_argument(
        "--id",
        default="",
        help="Triage id when --dir omitted (default: YYYY-MM-DD-ghostreader)",
    )
    parser.add_argument(
        "--export-history",
        default="",
        help="Optional history export path for 6-defer-resolved.json (e.g. history/audit-triage/<id>/buckets)",
    )
    args = parser.parse_args()

    from datetime import date

    repo = Path(__file__).resolve().parents[1]
    triage_id = args.id or f"{date.today().isoformat()}-ghostreader"
    triage_dir = Path(args.dir) if args.dir else repo / ".tmp" / "audit-triage" / triage_id
    ledger_path = triage_dir / "ledger.json"
    waves_dir = triage_dir / "defer-waves"

    if not ledger_path.is_file():
        print(f"Missing ledger: {ledger_path}", file=sys.stderr)
        return 1

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    defer_ids = {
        e["findingId"]
        for e in ledger
        if e.get("verdict") == "defer" or e.get("bucket") == "defer"
    }
    if not defer_ids:
        print("No defer rows in ledger.")
        return 0

    merged: dict[str, dict] = {}
    result_files = sorted(waves_dir.glob("result-wave-*.json"))
    if not result_files:
        print(f"No result-wave-*.json under {waves_dir}", file=sys.stderr)
        return 1

    for path in result_files:
        for row in json.loads(path.read_text(encoding="utf-8")):
            if "finalVerdict" not in row and "verdict" in row:
                row["finalVerdict"] = row["verdict"]
            if "finalBucket" not in row and "bucket" in row:
                row["finalBucket"] = row["bucket"]
            merged[row["findingId"]] = row

    missing = defer_ids - set(merged)
    if missing:
        print(f"Unresolved defer rows: {len(missing)}", file=sys.stderr)
        print("sample:", list(missing)[:5], file=sys.stderr)
        return 1

    by_id = {e["findingId"]: e for e in ledger}
    resolved_rows: list[dict] = []
    for fid in defer_ids:
        orig = by_id[fid]
        r = merged[fid]
        verdict = r["finalVerdict"]
        bucket = normalize_bucket(r.get("finalBucket", "reporting"))
        orig["verdict"] = verdict
        orig["bucket"] = bucket
        orig["evidence"] = r.get("evidence", orig.get("evidence", ""))
        if r.get("recommendedIssue") is not None:
            orig["recommendedIssue"] = r["recommendedIssue"]
        resolved_rows.append(
            {
                **orig,
                "finalVerdict": verdict,
                "finalBucket": bucket,
                "priorVerdict": "defer",
            }
        )

    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")

    remaining = sum(1 for e in ledger if e.get("verdict") == "defer")
    summary = {
        "originalDeferCount": len(defer_ids),
        "resolvedCount": len(resolved_rows),
        "deferRemaining": remaining,
        "byFinalVerdict": dict(Counter(r["finalVerdict"] for r in resolved_rows)),
        "byFinalBucket": dict(Counter(r["finalBucket"] for r in resolved_rows)),
    }
    (triage_dir / "defer-resolution-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    if args.export_history:
        export_dir = repo / args.export_history
        export_dir.mkdir(parents=True, exist_ok=True)
        payload = {"summary": summary, "findings": resolved_rows}
        (export_dir / "6-defer-resolved.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    print(json.dumps(summary, indent=2))
    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())