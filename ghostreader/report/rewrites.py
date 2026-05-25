"""Optional rewrite suggestions for Ghostreader reports.

When ``--show-rewrites`` is passed, this module generates alternative passages
for findings that include quoted evidence. Rewrites are framed as *one possible
alternative*, never as corrections — the tool is diagnostic, not prescriptive.
"""

from __future__ import annotations

from ghostreader.report import PrioritizedFinding, RewriteSuggestion

# ── Prompt template ──────────────────────────────────────────────────

_REWRITE_SYSTEM = """\
You are a prose craft assistant embedded in a literary analysis tool.
You will be given an original passage from a manuscript along with diagnostic
context about a concern identified by the analysis engine.

YOUR TASK: Produce ONE possible alternative passage that addresses the
diagnostic concern while preserving the author's voice, intent, and style
as closely as possible.

RULES:
- Frame the rewrite as an exploratory suggestion, not a correction.
- Keep the alternative roughly the same length as the original.
- Do NOT add new plot elements, characters, or information.
- Preserve the POV, tense, and tone of the original.
- Return ONLY the alternative passage text — no commentary, labels, or
  markdown formatting.
"""

_REWRITE_USER = """\
Diagnostic concern: {summary}
Dimension: {dimension}
Severity: {severity}

Original passage:
{evidence}
"""


# ── Public API ───────────────────────────────────────────────────────


async def generate_rewrites(
    findings: list[PrioritizedFinding],
    llm: object,
    *,
    max_rewrites: int = 5,
) -> list[RewriteSuggestion]:
    """Generate rewrite suggestions for findings that have evidence text.

    Only findings with non-empty ``evidence`` are eligible. At most
    ``max_rewrites`` suggestions are produced (prioritized by rank).

    Args:
        findings: Prioritized findings from the analysis.
        llm: A langchain ``BaseChatModel`` instance.
        max_rewrites: Cap on the number of rewrites to generate.

    Returns:
        List of ``RewriteSuggestion`` dataclasses.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    eligible = [f for f in findings if f.evidence.strip()]
    eligible = eligible[:max_rewrites]

    suggestions: list[RewriteSuggestion] = []

    for finding in eligible:
        user_msg = _REWRITE_USER.format(
            summary=finding.summary,
            dimension=finding.dimension,
            severity=finding.severity,
            evidence=finding.evidence,
        )

        try:
            response = await llm.ainvoke(  # type: ignore[union-attr]
                [
                    SystemMessage(content=_REWRITE_SYSTEM),
                    HumanMessage(content=user_msg),
                ]
            )
            alternative = str(response.content).strip()
        except Exception:
            # If the LLM call fails, skip this finding silently.
            continue

        if not alternative:
            continue

        suggestions.append(
            RewriteSuggestion(
                finding_rank=finding.rank,
                original=finding.evidence,
                alternative=alternative,
                rationale=f"Addresses {finding.severity} in {finding.dimension}: "
                f"{finding.summary}",
            )
        )

    return suggestions


def build_rewrite_rationale(finding: PrioritizedFinding) -> str:
    """Build a human-readable rationale string for a rewrite.

    Useful for renderers that want to explain why the rewrite was suggested.
    """
    return (
        f"This passage was flagged as a {finding.severity} "
        f"in {finding.dimension}: {finding.summary}"
    )


__all__ = ["build_rewrite_rationale", "generate_rewrites"]
