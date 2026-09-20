#!/usr/bin/env python3
"""Create GitHub issues for exported audit-triage buckets (Phase 6, Ghostreader)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HYGIENE = """
## Implementation hygiene

- **Code fix** with findingId (or file:line) referenced in the commit message
- **Regression test** under `tests/` (or nearest tests tree) that fails on pre-fix code
- Prefer focused pytest modules; keep slow/integration markers out of the default path
- After code lands: scoped `pytest` on touched tests (or project task check equivalent)
- Bucket 3 (reporting debt): prefer `.slizard/suppressions.yml` or upstream SLizard validator feedback — do not "fix" product code for pure FP
"""

BUCKETS = [
    (
        "1-confirmed-bugs-to-fix",
        "Ghostreader audit triage: confirmed bugs to fix ({n})",
        "Ship code fixes for verifier-confirmed defects.",
        True,
        True,
    ),
    (
        "2-likely-bugs",
        "Ghostreader audit triage: likely bugs ({n})",
        "Fix or short-verify likely-bug rows.",
        True,
        True,
    ),
    (
        "3-reporting-debt",
        "Ghostreader audit triage: reporting debt ({n})",
        "SLizard false/overstated/speculative noise — suppress or feed upstream; not product bugs.",
        True,
        True,
    ),
    (
        "4-appendix-noise",
        "Ghostreader audit triage: test appendix noise ({n})",
        "Bulk suppress via `.slizard/suppressions.yml` (or ignore on re-audit).",
        False,
        False,
    ),
    (
        "5-wontfix",
        "Ghostreader audit triage: wontfix candidates ({n})",
        "Accepted risk — record in `.slizard/suppressions.yml` or leave as wontfix disposition.",
        False,
        False,
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create GH issues per audit-triage bucket")
    parser.add_argument("--id", required=True, help="Export id under history/audit-triage/")
    parser.add_argument("--commit", required=True, help="Audit commit prefix from report")
    parser.add_argument(
        "--report-active",
        type=int,
        default=0,
        help="Active findings count from report summary (optional)",
    )
    parser.add_argument(
        "--ledger-total",
        type=int,
        default=0,
        help="Ledger row count (optional)",
    )
    parser.add_argument(
        "--note",
        default="",
        help="Extra context paragraph for issue bodies",
    )
    parser.add_argument(
        "--note-file",
        default="",
        help="Read --note from file (avoids shell quoting issues)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Write bodies only, no gh")
    args = parser.parse_args()
    if args.note_file:
        note_path = Path(args.note_file)
        if not note_path.is_file():
            print(f"Missing note file: {note_path}", file=sys.stderr)
            return 1
        args.note = note_path.read_text(encoding="utf-8").strip()

    repo = Path(__file__).resolve().parents[1]
    base = f"history/audit-triage/{args.id}"
    export_root = repo / base
    if not export_root.is_dir():
        print(f"Missing export: {export_root}", file=sys.stderr)
        return 1

    diff_path = f"history/audit-triage/{args.id}-diff"
    has_diff = (repo / diff_path).is_dir()
    diff_note = ""
    if has_diff:
        diff_note = (
            f"\r\n## Diff scope\r\n\r\n"
            f"Prioritization lens: `{diff_path}/` (report `ghostreader-audit.new.md`).\r\n"
        )

    note_block = f"\r\n{args.note}\r\n" if args.note else ""
    active_s = (
        f"{args.report_active} active in report"
        if args.report_active
        else "see outcome.md"
    )
    ledger_s = f"{args.ledger_total} in ledger" if args.ledger_total else "see outcome.md"

    created: list[list[str]] = []
    for bucket_file, title_tpl, action, hygiene, diff_link in BUCKETS:
        bucket_path = export_root / "buckets" / f"{bucket_file}.json"
        if not bucket_path.is_file():
            print(f"skip missing {bucket_file}")
            continue
        payload = json.loads(bucket_path.read_text(encoding="utf-8"))
        count = int(payload.get("count", 0))
        if count == 0:
            print(f"skip empty {bucket_file}")
            continue

        title = title_tpl.format(n=count)
        body = f"""## Context

Ghostreader SLizard-audit triage on commit `{args.commit}` ({active_s}; {ledger_s}).
Orchestrated via `.grok/skills/audit-triage/`. Export id: `{args.id}`.{note_block}

## Bucket

- **{bucket_file}** — {count} findings
- **Action:** {action}

## Artifacts

- Machine ledger: `{base}/buckets/{bucket_file}.json`
- Human synthesis: `{base}/outcome.md`
- Export README: `{base}/README.md`
{diff_note if diff_link and has_diff else ""}
## Acceptance

- All {count} rows in this bucket addressed per action above
- Cross-link commits to this issue
{HYGIENE if hygiene else ""}"""

        body_path = repo / ".tmp" / f"issue-{bucket_file}.md"
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_text(body, encoding="utf-8")

        if args.dry_run:
            print(f"dry-run {title} -> {body_path}")
            continue

        r = subprocess.run(
            ["gh", "issue", "create", "--title", title, "--body-file", str(body_path)],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            print(f"FAIL {title}: {r.stderr}", file=sys.stderr)
            return 1
        url = r.stdout.strip()
        num = url.rstrip("/").split("/")[-1]
        created.append([num, title])
        print(num, title)

    out = repo / ".tmp" / f"issue-ids-{args.id}.json"
    out.write_text(json.dumps(created, indent=2), encoding="utf-8")
    print(json.dumps({"created": len(created), "path": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
