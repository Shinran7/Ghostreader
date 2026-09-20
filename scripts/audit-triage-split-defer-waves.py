#!/usr/bin/env python3
"""Split defer rows from triage ledger into resolution waves."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def wave_for(item: dict) -> int:
    fp = item["filePath"]
    sev = item["severity"]
    ev = (item.get("evidence") or "").lower()
    cat = item.get("category", "").lower()

    if sev in ("P1", "P2"):
        return 1
    if (
        fp.startswith("scripts/")
        or "/scripts/" in fp
        or fp in (
            "Dockerfile",
            "docker-compose.yml",
            "fly.toml",
            "pnpm-lock.yaml",
            "package-lock.json",
            "poetry.lock",
        )
        or fp.startswith("fly.")
        or fp.startswith(".github/")
        or fp.startswith(".githooks/")
    ):
        return 4
    if (
        "/validators/" in fp
        or "fp-suppress" in fp
        or "/detectors/" in fp
        or "heuristic" in ev
        or "false positive" in ev
        or "brittle" in ev
        or "overly broad" in cat
    ):
        return 3
    return 2


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
    args = parser.parse_args()

    from datetime import date

    repo = Path(__file__).resolve().parents[1]
    triage_id = args.id or f"{date.today().isoformat()}-ghostreader"
    triage_dir = Path(args.dir) if args.dir else repo / ".tmp" / "audit-triage" / triage_id
    ledger_path = triage_dir / "ledger.json"
    if not ledger_path.is_file():
        print(f"Missing ledger: {ledger_path}", file=sys.stderr)
        return 1

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    defer_rows = [e for e in ledger if e.get("verdict") == "defer" or e.get("bucket") == "defer"]
    if not defer_rows:
        print("No defer rows in ledger; skipping wave split.")
        return 0

    waves: dict[int, list] = {1: [], 2: [], 3: [], 4: []}
    for item in defer_rows:
        waves[wave_for(item)].append(item)

    out_dir = triage_dir / "defer-waves"
    out_dir.mkdir(parents=True, exist_ok=True)
    for n, batch in waves.items():
        path = out_dir / f"wave-{n}.json"
        path.write_text(json.dumps(batch, indent=2), encoding="utf-8")
        print(f"wave-{n}: {len(batch)}")

    summary = {"deferCount": len(defer_rows), "waves": {str(k): len(v) for k, v in waves.items()}}
    (out_dir / "wave-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())