"""JSON export for Ghostreader analysis reports.

Produces structured JSON output matching the internal analysis model,
suitable for scripting and downstream tool integration.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from ghostreader.report import ReportOutput


def export_json(
    report: ReportOutput,
    *,
    output: TextIO | None = None,
    output_path: Path | None = None,
    indent: int = 2,
) -> str:
    """Serialize the report as JSON.

    Writes to ``output`` (a file-like, defaults to stdout) or to
    ``output_path`` if provided. Always returns the JSON string.

    Args:
        report: The typed report to serialize.
        output: Writable file-like; defaults to sys.stdout.
        output_path: If given, write JSON to this file (creates parent dirs).
        indent: JSON indentation level.

    Returns:
        The JSON string.
    """
    payload = _build_payload(report)
    text = json.dumps(payload, indent=indent, ensure_ascii=False)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    elif output is not None:
        output.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")

    return text


# ── Payload construction ─────────────────────────────────────────────


def _build_payload(report: ReportOutput) -> dict[str, Any]:
    """Build the JSON-serializable dict from a ReportOutput."""
    return {
        "ghostreader_version": "0.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manuscript_name": report.manuscript_name,
        "executive_summary": report.executive_summary,
        "overview": {
            "total_findings": report.total_findings,
            "strengths_count": report.strengths_count,
            "concerns_count": report.concerns_count,
        },
        "dimension_ratings": [
            asdict(dr) for dr in report.dimension_ratings
        ],
        "prioritized_findings": [
            asdict(f) for f in report.prioritized_findings
        ],
        "rewrite_suggestions": [
            asdict(s) for s in report.rewrite_suggestions
        ] if report.rewrite_suggestions else [],
    }


__all__ = ["export_json"]
