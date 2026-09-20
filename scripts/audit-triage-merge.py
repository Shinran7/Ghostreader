#!/usr/bin/env python3
"""Merge verifier batch results into ledger and emit outcome.md."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


def load_results(dir_path: Path) -> list[dict]:
    rows = []
    for p in sorted(dir_path.glob("result-batch-*.json")):
        rows.extend(json.loads(p.read_text(encoding="utf-8")))
    return rows


def normalize_bucket(b: str) -> str:
    if b in ("fix", "reporting", "wontfix", "defer"):
        return b
    if b in ("infra", "maintainability", "security", "prompt-budget", "static-analysis"):
        return "fix" if b in ("security", "prompt-budget", "static-analysis") else "reporting"
    return "reporting"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dir",
        default="",
        help="Triage dir under .tmp/audit-triage (default: today's Ghostreader)",
    )
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    triage_dir = (
        Path(args.dir)
        if args.dir
        else repo / ".tmp" / "audit-triage" / f"{date.today().isoformat()}-ghostreader"
    )
    ledger = json.loads((triage_dir / "ledger.json").read_text(encoding="utf-8"))
    results = load_results(triage_dir / "results")
    by_id = {r["findingId"]: r for r in results}

    for e in ledger:
        if e["findingId"] in by_id:
            r = by_id[e["findingId"]]
            e["verdict"] = r.get("verdict")
            e["bucket"] = normalize_bucket(r.get("bucket", "reporting"))
            e["evidence"] = r.get("evidence", "")

    (triage_dir / "ledger.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")

    fix_verdicts = {"confirmed-bug", "likely-bug"}
    reporting_verdicts = {
        "false-positive",
        "overstated",
        "speculative",
        "duplicate",
        "bad-anchor",
        "appendix-noise",
    }

    # Exclusive membership: fix > wontfix > reporting (avoid double-count in outcome.md).
    bugs: list[dict] = []
    wontfix: list[dict] = []
    reporting: list[dict] = []
    pending: list[dict] = []
    for e in ledger:
        verdict = e.get("verdict")
        bucket = e.get("bucket")
        if not verdict:
            pending.append(e)
        elif verdict in fix_verdicts or bucket == "fix":
            bugs.append(e)
        elif verdict == "wontfix" or bucket == "wontfix":
            wontfix.append(e)
        elif verdict in reporting_verdicts or bucket == "reporting":
            reporting.append(e)
        else:
            reporting.append(e)

    sev_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    bugs.sort(key=lambda e: (sev_order.get(e["severity"], 9), -e.get("confidence", 0)))

    lines = [
        "# Ghostreader SLizard-Audit Triage Outcome",
        "",
        f"- Total findings: {len(ledger)}",
        f"- Verified bugs to fix: {len(bugs)}",
        f"- Reporting debt (SLizard noise / overstated): {len(reporting)}",
        f"- Wontfix candidates: {len(wontfix)}",
        f"- Still pending: {len(pending)}",
        "",
        "## 1. BUGS WE NEED TO FIX",
        "",
    ]
    for e in bugs:
        lines.append(
            f"- **{e['severity']}** `{e['filePath']}:{e['line']}` — {e.get('message') or e['category']} "
            f"({e.get('verdict')}: {e.get('evidence', '')})"
        )

    lines.extend(["", "## 2. REPORTING DEBT (SLizard false / overstated)", ""])
    by_lever: dict[str, list] = defaultdict(list)
    for e in reporting:
        v = e.get("verdict") or "unknown"
        by_lever[v].append(e)
    for lever, items in sorted(by_lever.items(), key=lambda x: -len(x[1])):
        lines.append(f"### {lever} ({len(items)})")
        for e in items[:25]:
            lines.append(
                f"- `{e['filePath']}:{e['line']}` — {e.get('evidence') or e.get('message', '')[:120]}"
            )
        if len(items) > 25:
            lines.append(f"- … and {len(items) - 25} more")
        lines.append("")

    lines.extend(["", "## 3. WONTFIX CANDIDATES", ""])
    for e in wontfix[:40]:
        lines.append(f"- `{e['filePath']}:{e['line']}` — {e.get('evidence', e.get('message', ''))[:120]}")
    if len(wontfix) > 40:
        lines.append(f"- … and {len(wontfix) - 40} more")

    (triage_dir / "outcome.md").write_text("\n".join(lines), encoding="utf-8")

    summary = {
        "bugs": len(bugs),
        "reporting": len(reporting),
        "wontfix": len(wontfix),
        "pending": len(pending),
        "verdicts": dict(Counter(e.get("verdict") or "pending" for e in ledger)),
    }
    (triage_dir / "outcome-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())