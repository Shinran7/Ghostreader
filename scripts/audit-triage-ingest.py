#!/usr/bin/env python3
"""Ingest SLizard audit markdown (Ghostreader consumer) into a triage ledger.

Default path is markdown-only (no training/self-labels.json). Optional
--self-labels points at a SLizard self-labels store when joining findingIds
from a deferred self-audit row set — rarely used for Ghostreader.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

# Confidence % is optional — newer audit markdown omits [N%] after severity.
FINDING_RE = re.compile(
    r"^- \*\*(P[0-3])\*\*(?:\s+\[(\d+)%\])?\s+`([^`]+):(\d+)`\s*[\u2014\u2013\-]\s*(.+?)(?:\s+\[|$)",
    re.MULTILINE,
)
SECTION_RE = re.compile(r"^## (.+)$", re.MULTILINE)
FILE_HEAD_RE = re.compile(r"^### (.+?) \((\d+ .+)\)$", re.MULTILINE)
# Prefer known pipeline annotations over every incidental `[bracket]` in prose.
KNOWN_ANNOTATION_MARKER_RE = re.compile(
    r"\[("
    r"(?:capped|demoted|rewritten|attenuated|penalized|corroborated)"
    r":[^\]]+"
    r")\]",
    re.IGNORECASE,
)
# Confidence percent tokens like [85%] — not pipeline annotations.
CONFIDENCE_BRACKET_RE = re.compile(r"\[\d+%\]")


@dataclass
class ParsedFinding:
    severity: str
    confidence: int
    file_path: str
    line: int
    message: str
    section: str
    file_group: str
    markers: list[str] = field(default_factory=list)
    category: str = ""
    suggestion: str = ""

    def finding_id(self) -> str:
        parts = [self.file_path, str(self.line), self.category, self.message]
        return hashlib.sha1("\0".join(parts).encode()).hexdigest()[:16]


def extract_annotation_markers(text: str) -> list[str]:
    """Extract only known pipeline annotation markers from a finding line/body."""
    return [m.group(1).strip() for m in KNOWN_ANNOTATION_MARKER_RE.finditer(text)]


def parse_markdown(md: str) -> list[ParsedFinding]:
    findings: list[ParsedFinding] = []
    current_section = "Unknown"
    current_group = ""

    for raw_line in md.splitlines():
        sec = SECTION_RE.match(raw_line)
        if sec:
            current_section = sec.group(1).strip()
            continue
        head = FILE_HEAD_RE.match(raw_line)
        if head:
            current_group = head.group(1).strip()
            continue
        m = FINDING_RE.match(raw_line)
        if not m:
            continue
        severity, conf, fp, line_s, message = m.groups()
        # FINDING_RE stops message before trailing `[capped: …]`; scan full line.
        markers = extract_annotation_markers(raw_line)
        if not markers:
            markers = extract_annotation_markers(message)
        cat_m = re.search(r"\*\(([^)]+)\)\*\s*$", raw_line)
        category = cat_m.group(1) if cat_m else ""
        clean_msg = KNOWN_ANNOTATION_MARKER_RE.sub("", message)
        clean_msg = CONFIDENCE_BRACKET_RE.sub("", clean_msg).strip()
        clean_msg = re.sub(r"\*\([^)]+\)\*\s*$", "", clean_msg).strip()
        findings.append(
            ParsedFinding(
                severity=severity,
                confidence=int(conf) if conf else 60,
                file_path=fp,
                line=int(line_s),
                message=clean_msg,
                section=current_section,
                file_group=current_group,
                markers=markers,
                category=category,
            )
        )
    return findings


def load_self_labels(path: Path, commit_prefix: str) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for row in data.get("labels", []) or []:
        ch = row.get("commitHash") or ""
        if not ch.startswith(commit_prefix):
            continue
        if row.get("outcome") != "deferred":
            continue
        out.append(row)
    return out


def ledger_from_parsed(parsed: list[ParsedFinding], commit_prefix: str) -> list[dict[str, Any]]:
    """Build ledger from markdown when self-labels has no deferred rows for this commit."""
    ledger = []
    for p in parsed:
        ledger.append(
            {
                "findingId": p.finding_id(),
                "severity": p.severity,
                "confidence": p.confidence,
                "filePath": p.file_path,
                "line": p.line,
                "category": p.category,
                "section": p.section,
                "message": p.message,
                "markers": p.markers,
                "hasMarkdown": True,
                "verdict": None,
                "evidence": "",
                "bucket": None,
                "auditCommit": commit_prefix,
            }
        )
    return ledger


def join_rows(parsed: list[ParsedFinding], labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, int, str], list[ParsedFinding]] = defaultdict(list)
    for p in parsed:
        by_key[(p.file_path, p.line, p.severity)].append(p)

    ledger = []
    for lab in labels:
        key = (lab["filePath"], lab["line"], lab["severity"])
        candidates = by_key.get(key, [])
        match = None
        for c in candidates:
            if c.category and lab["category"] and c.category.lower() in lab["category"].lower():
                match = c
                break
        if match is None and candidates:
            match = candidates[0]

        category = (match.category if match and match.category else None) or lab.get("category") or ""

        entry = {
            "findingId": lab["findingId"],
            "severity": lab["severity"],
            "confidence": lab.get("rawConfidence", 0),
            "filePath": lab["filePath"],
            "line": lab["line"],
            "category": category,
            "section": match.section if match else infer_section(lab),
            "message": match.message if match else "",
            "markers": match.markers if match else [],
            "hasMarkdown": match is not None,
            "verdict": None,
            "evidence": "",
            "bucket": None,
        }
        ledger.append(entry)
    return ledger


def infer_section(lab: dict[str, Any]) -> str:
    fp = lab["filePath"]
    cat = lab["category"].lower()
    if _is_test_path(fp) or "test" in cat:
        return "Test Quality (Appendix)"
    if "dependency" in cat:
        return "Dependency Hygiene (Appendix)"
    if fp in ("pnpm-lock.yaml", "Dockerfile", "docker-compose.yml", "fly.toml") or fp.startswith(
        "fly."
    ):
        return "Findings"
    return "Findings"


def _is_test_path(fp: str) -> bool:
    """Unit/integration test files under Ghostreader layout."""
    norm = fp.replace("\\", "/")
    if norm.startswith("tests/") or "/tests/" in norm:
        return True
    base = norm.rsplit("/", 1)[-1]
    return (base.startswith("test_") and base.endswith(".py")) or base.endswith("_test.py")


def _is_operator_cli_path(fp: str) -> bool:
    norm = fp.replace("\\", "/")
    return (
        norm.startswith("scripts/")
        or norm.startswith("tools/")
        or "/scripts/" in norm
    )


def _is_security_priority(sev: str, cat: str, msg: str) -> bool:
    """Conservative gate — do not blanket-wontfix P0/P1 security on scripts/*."""
    if sev not in ("P0", "P1"):
        return False
    hay = f"{cat} {msg}".lower()
    return bool(
        re.search(
            r"\b(?:security|cwe-\d+|injection|xss|ssrf|rce|path\s*traversal|"
            r"command\s*injection|prototype\s*pollution|hardcoded\s*secret|"
            r"credential|auth(?:n|z|entication|orization)?)\b",
            hay,
        )
    )


def _is_cli_or_operator_path(fp: str) -> bool:
    """scripts/tools plus src/cli operator entrypoints."""
    norm = fp.replace("\\", "/")
    if _is_operator_cli_path(norm):
        return True
    return bool(re.search(r"(?:^|/)cli/", norm))


def _is_detector_self_path(fp: str) -> bool:
    """Deterministic check / detector / recall-check modules (self-scan surface)."""
    norm = fp.replace("\\", "/")
    base = norm.rsplit("/", 1)[-1]
    if base.endswith("-check.ts") or base.endswith("-check.tsx"):
        return True
    if any(p.endswith("-check") for p in norm.split("/")):
        return True
    if re.search(r"/reviewer/detectors/detectors-[^/]+\.tsx?$", norm, re.I):
        return True
    if base.endswith("-recall-check.ts") or base.endswith("-recall-check.tsx"):
        return True
    if re.search(
        r"/validators/(?:content-filters|intentional-comment|heuristics)[^/]*\.ts$",
        norm,
        re.I,
    ):
        return True
    return False


def _scripts_hygiene_rule(fp: str, sev: str, cat: str, msg: str) -> dict[str, str] | None:
    """
    Path heuristics for scripts/tools hygiene clusters without requiring cap markers.
    (r3: rule pre-pass ruled 0 because markers were empty / not extracted.)
    """
    if not _is_operator_cli_path(fp):
        return None
    if _is_security_priority(sev, cat, msg):
        return None

    # Report clocks / generatedAt / toISOString non-determinism
    if re.search(
        r"\b(?:generatedat|toisostring|new\s+date\s*\(|non[- ]?deterministic|"
        r"report\s+clock|timestamp\s+(?:in|for)\s+(?:report|output|json))\b",
        msg,
    ):
        return verdict(
            "wontfix",
            "wontfix",
            "CLI report clock / generatedAt — accepted operational non-determinism",
        )

    # path.split("/").pop() basename extract after normalize
    if re.search(
        r"path\.split\s*\(|\.split\s*\(\s*['\"]\/['\"]\s*\)|basename|"
        r"\.pop\s*\(\s*\)\s*(?:for\s+)?(?:basename|filename|file\s*name)",
        msg,
    ) or ("path.split" in msg and (".pop" in msg or "basename" in msg)):
        return verdict(
            "false-positive",
            "reporting",
            "path.split('/').pop() after normalize — intentional basename extract",
        )

    # eslint-disable / @ts-ignore / type-suppress-added intentional suppressions
    if re.search(
        r"eslint-disable|@ts-ignore|@ts-expect-error|@ts-nocheck|"
        r"type/lint\s+suppression|suppression\s+directive|type-suppress",
        msg,
    ):
        return verdict(
            "wontfix",
            "wontfix",
            "eslint-disable/@ts-ignore in CLI tooling — accepted local suppress",
        )

    # Empty if / empty control-flow body on operator scripts (hygiene stubs)
    if re.search(
        r"empty\s+(?:if|else)(?:-block)?\s+body|empty-body-control-flow|"
        r"only\s+comments,?\s+no\s+executable",
        msg,
    ):
        return verdict(
            "wontfix",
            "wontfix",
            "Empty if/else comment-only body on CLI script — hygiene / no-op stub",
        )

    # Mid-file static imports after executable code (secrets load, dotenv, etc.)
    if re.search(
        r"(?:static\s+)?import\s+(?:added\s+)?after\s+executable|"
        r"imports?\s+should\s+be\s+at\s+the\s+top|"
        r"mid[- ]file\s+import|import\s+after\s+(?:secrets?|dotenv|executable)",
        msg,
    ):
        return verdict(
            "wontfix",
            "wontfix",
            "Mid-file import after secrets/dotenv load — intentional CLI bootstrap order",
        )

    # execSync / spawnSync shell templates in operator scripts
    if re.search(
        r"\b(?:execsync|spawnsync|child_process|shell\s+template|"
        r"shell\s*(?:command|string|interpolation)|"
        r"command\s+injection\s+via\s+(?:template|string))\b",
        msg,
    ) and not _is_security_priority(sev, cat, msg):
        # P2/P3 shell noise on scripts; P0/P1 with security language already gated above
        if sev in ("P2", "P3") or "security" not in cat:
            return verdict(
                "wontfix",
                "wontfix",
                "execSync/spawnSync shell template in operator CLI — accepted risk",
            )

    # Single-process / no concurrent callers (legacy path)
    if "single-process" in msg or "single process" in msg or "single operator" in msg:
        return verdict("wontfix", "wontfix", "CLI/script single-process — accepted operational risk")

    return None


def _phase3_audit_hygiene_rule(
    fp: str, sev: str, cat: str, msg: str
) -> dict[str, str] | None:
    """
    Phase 3 (#2019) audit-only clusters: empty-if, type-suppress, generatedAt,
    detector self-scan — rule without requiring cap markers so r5 pre-pass > 0.
    """
    if _is_security_priority(sev, cat, msg):
        return None

    # generatedAt / report clocks on CLI, scorecard, census, config-manifest
    if re.search(
        r"\b(?:generatedat|toisostring|report\s+clock|non[- ]?deterministic)\b",
        msg,
    ) and (
        "generatedat" in msg
        or "toisostring" in msg
        or "report clock" in msg
        or "new date" in msg
    ):
        if _is_cli_or_operator_path(fp) or re.search(
            r"(?:scorecard|census|inventory|pipeline-ledger|extract-lab|"
            r"maze-|recall-miss|config-manifest)",
            fp,
            re.I,
        ):
            return verdict(
                "wontfix",
                "wontfix",
                "CLI report clock / generatedAt — accepted operational non-determinism",
            )

    # type-suppress-added / lint suppress on CLI or detector regex catalogs
    if re.search(
        r"type/lint\s+suppression\s+directive|added\s+type/lint\s+suppression|"
        r"suppression\s+directive|type-suppress-added",
        msg,
    ) or re.search(
        r"eslint-disable|@ts-ignore|@ts-expect-error|@ts-nocheck",
        msg,
    ):
        if _is_cli_or_operator_path(fp):
            return verdict(
                "wontfix",
                "wontfix",
                "eslint-disable/@ts-ignore in CLI tooling — accepted local suppress",
            )
        if _is_detector_self_path(fp):
            return verdict(
                "false-positive",
                "reporting",
                "type/lint suppress mention is detector regex/JSDoc catalog — not product suppress",
            )

    # Empty if/else comment-only on detector modules (intentional stubs)
    if re.search(
        r"empty\s+(?:if|else)(?:-block)?\s+body|empty-body-control-flow|"
        r"only\s+comments,?\s+no\s+executable",
        msg,
    ):
        if _is_detector_self_path(fp):
            return verdict(
                "false-positive",
                "reporting",
                "Empty if comment-only stub on detector module — hygiene, not forgotten product logic",
            )
        if _is_cli_or_operator_path(fp):
            return verdict(
                "wontfix",
                "wontfix",
                "Empty if/else comment-only body on CLI script — hygiene / no-op stub",
            )

    return None


def rule_classify(entry: dict[str, Any]) -> dict[str, Any] | None:
    fp = entry["filePath"]
    sev = entry["severity"]
    cat = entry["category"].lower()
    raw_msg = entry.get("message") or ""
    msg = raw_msg.lower()
    markers = [m.lower() for m in entry.get("markers", [])]
    # Re-extract from message body when markers list is empty (self-labels path
    # or older parses that stripped caps).
    if not markers:
        markers = [m.lower() for m in extract_annotation_markers(raw_msg)]

    if entry["section"] == "Test Quality (Appendix)" or _is_test_path(fp):
        return verdict("appendix-noise", "reporting", "Test-file hygiene; capped appendix row")

    if "dependency hygiene" in cat or "cwe-1395" in cat:
        if "pnpm-lock.yaml" in fp and sev == "P1":
            return None  # verify GHSA
        return verdict("overstated", "reporting", "Dependency appendix / lockfile hygiene")

    if any("capped: self-audited test file" in m for m in markers):
        return verdict("appendix-noise", "reporting", "Self-audited test cap")

    if any("capped: test-quality" in m for m in markers):
        return verdict("appendix-noise", "reporting", "Test-quality cap")

    if any("capped: lint" in m for m in markers) or entry["section"] == "Lint & Style (Appendix)":
        return verdict("appendix-noise", "reporting", "Lint/style appendix")

    if any("capped: infrastructure speculative" in m for m in markers):
        return verdict("wontfix", "wontfix", "Infra prerequisite speculation — document don’t fix")

    # Cap marker OR message-body text even when markers list empty (r3 miss).
    if (
        any("capped: cli-script-context" in m for m in markers)
        or "[capped: cli-script-context]" in msg
        or (fp.startswith("scripts/") and "single-process" in msg)
    ):
        return verdict("wontfix", "wontfix", "CLI/script context — accepted operational risk")

    # scripts/tools hygiene clusters without requiring cap markers (Phase 0b / #2019).
    hygiene = _scripts_hygiene_rule(fp, sev, cat, msg)
    if hygiene is not None:
        return hygiene

    # Phase 3 A1–A3 audit-only FP clusters (empty-if / type-suppress / clocks).
    phase3 = _phase3_audit_hygiene_rule(fp, sev, cat, msg)
    if phase3 is not None:
        return phase3

    if any("capped: audit-concurrency-speculation" in m for m in markers):
        return verdict("wontfix", "wontfix", "Audit CLI concurrency speculation")

    if any("capped: heuristic-completeness advisory" in m for m in markers):
        return verdict("appendix-noise", "reporting", "Heuristic completeness advisory")

    if any("capped: detector-self-scan" in m for m in markers) or (
        "[capped: detector-self-scan]" in msg
    ):
        return verdict(
            "false-positive",
            "reporting",
            "Detector self-scan of docs/templates/pattern catalog",
        )

    if any("positive observation" in m for m in markers):
        return verdict("appendix-noise", "reporting", "Positive observation style")

    if any("systemic:" in m for m in markers) and sev in ("P2", "P3"):
        return None  # verify representative

    if "sha-1" in msg and "cryptographically broken" in msg:
        return verdict("false-positive", "reporting", "SHA-1 used for non-crypto IDs — not a bug")

    if "fly.toml" in fp or fp.startswith("fly.") or "docker-compose" in fp:
        if sev == "P3":
            return verdict("wontfix", "wontfix", "Deployment config assumption — ops concern")

    return None


def verdict(v: str, bucket: str, evidence: str) -> dict[str, str]:
    return {"verdict": v, "bucket": bucket, "evidence": evidence}


def batch_entries(ledger: list[dict[str, Any]], size: int = 20) -> list[list[dict[str, Any]]]:
    pending = [e for e in ledger if e["verdict"] is None]
    # priority: security section, P1, P2, P3
    def pri(e: dict[str, Any]) -> tuple[int, int, str]:
        sec = 0 if "Security" in e["section"] else 1
        sev = {"P1": 0, "P2": 1, "P3": 2}.get(e["severity"], 3)
        return (sec, sev, e["filePath"])

    pending.sort(key=pri)
    return [pending[i : i + size] for i in range(0, len(pending), size)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default="",
        help="Path to diff audit markdown report (<slug>-audit.new.md). "
        "Default: <repo>/../ghostreader-audit.new.md when that file exists.",
    )
    parser.add_argument(
        "--commit",
        default="",
        help="Audit commit prefix (default: parsed from report / .slizard manifest / HEAD)",
    )
    parser.add_argument(
        "--id",
        default="",
        help="Triage id under .tmp/audit-triage/ (default: YYYY-MM-DD-ghostreader)",
    )
    parser.add_argument(
        "--scope-markdown",
        choices=("auto", "on", "off"),
        default="auto",
        help="Keep only findings present in the markdown report (auto: on for *.new.md)",
    )
    parser.add_argument(
        "--self-labels",
        default="",
        help="Optional path to self-labels.json (SLizard self-audit only; omit for Ghostreader)",
    )
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    if args.report:
        md_path = Path(args.report)
    else:
        candidate = repo.parent / "ghostreader-audit.new.md"
        md_path = candidate if candidate.is_file() else repo / "ghostreader-audit.new.md"
    triage_id = args.id or f"{date.today().isoformat()}-ghostreader"
    out_dir = repo / ".tmp" / "audit-triage" / triage_id
    out_dir.mkdir(parents=True, exist_ok=True)

    md = md_path.read_text(encoding="utf-8")
    commit_prefix = args.commit[:8] if args.commit else ""
    if not args.commit:
        m = re.search(r"current audit commit: ([0-9a-f]+)", md)
        if m:
            commit_prefix = m.group(1)[:8]
        else:
            # Prefer SLizard consumer audit manifest when present.
            manifest = repo / ".slizard" / "audit-run-manifest.json"
            if manifest.is_file():
                try:
                    ch = json.loads(manifest.read_text(encoding="utf-8")).get("commitHash") or ""
                    if ch:
                        commit_prefix = ch[:8]
                except (OSError, json.JSONDecodeError, TypeError, ValueError):
                    pass
            if not commit_prefix:
                import subprocess

                try:
                    head = subprocess.check_output(
                        ["git", "rev-parse", "--short=8", "HEAD"],
                        cwd=repo,
                        text=True,
                        timeout=30,
                    ).strip()
                    if head:
                        commit_prefix = head
                except (OSError, subprocess.SubprocessError, TimeoutError):
                    commit_prefix = "unknown"

    parsed = parse_markdown(md)
    labels_path = Path(args.self_labels) if args.self_labels else repo / "training" / "self-labels.json"
    labels = load_self_labels(labels_path, commit_prefix)
    if labels:
        ledger = join_rows(parsed, labels)
    else:
        ledger = ledger_from_parsed(parsed, commit_prefix)

    scope_md = args.scope_markdown
    if scope_md == "auto":
        scope_md = "on" if md_path.name.endswith(".new.md") else "off"
    out_of_scope = 0
    if scope_md == "on":
        before = len(ledger)
        ledger = [e for e in ledger if e.get("hasMarkdown")]
        out_of_scope = before - len(ledger)

    for e in ledger:
        ruled = rule_classify(e)
        if ruled:
            e.update(ruled)

    batches = batch_entries(ledger)
    for i, batch in enumerate(batches):
        (out_dir / "batches" / f"batch-{i:03d}.json").parent.mkdir(parents=True, exist_ok=True)
        (out_dir / "batches" / f"batch-{i:03d}.json").write_text(
            json.dumps(batch, indent=2), encoding="utf-8"
        )

    summary = {
        "triageId": triage_id,
        "auditCommit": commit_prefix,
        "ledgerSource": "self-labels" if labels else "markdown",
        "total": len(ledger),
        "markdownParsed": len(parsed),
        "withMessage": sum(1 for e in ledger if e["hasMarkdown"]),
        "ruled": sum(1 for e in ledger if e["verdict"]),
        "pending": sum(1 for e in ledger if not e["verdict"]),
        "batches": len(batches),
        "byVerdict": {},
        "scopedToNewMarkdown": scope_md == "on",
        "outOfScopeDeferredNoMarkdown": out_of_scope,
    }
    for e in ledger:
        v = e["verdict"] or "pending"
        summary["byVerdict"][v] = summary["byVerdict"].get(v, 0) + 1

    (out_dir / "ledger.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())