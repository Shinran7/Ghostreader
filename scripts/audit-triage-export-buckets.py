#!/usr/bin/env python3
"""Export six triage buckets to history/ for issue linking."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

FIELDS = (
    "findingId",
    "severity",
    "filePath",
    "line",
    "category",
    "verdict",
    "bucket",
    "evidence",
    "message",
)


def slim(entry: dict) -> dict:
    return {k: entry[k] for k in FIELDS if entry.get(k)}


def bucket_map(ledger: list[dict]) -> dict[str, list[dict]]:
    return {
        "1-confirmed-bugs-to-fix": [e for e in ledger if e.get("verdict") == "confirmed-bug"],
        "2-likely-bugs": [e for e in ledger if e.get("verdict") == "likely-bug"],
        "3-reporting-debt": [
            e
            for e in ledger
            if e.get("verdict")
            in ("false-positive", "overstated", "speculative", "bad-anchor", "duplicate")
        ],
        "4-appendix-noise": [e for e in ledger if e.get("verdict") == "appendix-noise"],
        "5-wontfix": [
            e for e in ledger if e.get("verdict") == "wontfix" or e.get("bucket") == "wontfix"
        ],
        "6-defer": [e for e in ledger if e.get("verdict") == "defer"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dir",
        default="",
        help="Triage dir under .tmp/audit-triage (default: history id under .tmp)",
    )
    parser.add_argument(
        "--id",
        default="",
        help="Export id folder name under history/audit-triage/ (default: YYYY-MM-DD-ghostreader)",
    )
    parser.add_argument(
        "--commit",
        default="",
        help="Audit commit prefix from report summary / .slizard manifest",
    )
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    export_id = args.id or f"{date.today().isoformat()}-ghostreader"
    triage_dir = Path(args.dir).resolve() if args.dir else repo / ".tmp" / "audit-triage" / export_id
    ledger_path = triage_dir / "ledger.json"
    if not ledger_path.is_file():
        print(f"Missing ledger: {ledger_path}", file=sys.stderr)
        return 1

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    commit = args.commit
    if not commit:
        summary_path = triage_dir / "summary.json"
        if summary_path.is_file():
            try:
                commit = str(json.loads(summary_path.read_text(encoding="utf-8")).get("auditCommit") or "")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                commit = ""
        if not commit and ledger:
            commit = str(ledger[0].get("auditCommit") or "")
    if not commit:
        commit = "unknown"

    export_root = repo / "history" / "audit-triage" / export_id
    buckets_dir = export_root / "buckets"
    buckets_dir.mkdir(parents=True, exist_ok=True)

    grouped = bucket_map(ledger)
    manifest: dict[str, int] = {}
    for name, items in grouped.items():
        payload = {
            "bucket": name,
            "count": len(items),
            "auditCommit": commit,
            "triageDir": str(triage_dir.relative_to(repo)).replace("\\", "/"),
            "findings": [slim(e) for e in items],
        }
        out = buckets_dir / f"{name}.json"
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        manifest[name] = len(items)

    for name in ("outcome.md", "outcome-summary.json", "summary.json"):
        src = triage_dir / name
        if src.is_file():
            shutil.copy2(src, export_root / name)

    readme = export_root / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Audit triage export (Ghostreader)",
                "",
                f"- Audit commit: `{commit}`",
                f"- Total findings: {len(ledger)}",
                f"- Scratch ledger: `{triage_dir.relative_to(repo).as_posix()}/ledger.json`",
                "",
                "## Buckets",
                "",
            ]
            + [f"- `{name}`: {count} findings → `buckets/{name}.json`" for name, count in manifest.items()]
            + ["", "## Synthesis", "", "- `outcome.md` — human summary", ""]
        ),
        encoding="utf-8",
    )

    print(json.dumps({"exportRoot": str(export_root.relative_to(repo)), "buckets": manifest}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())