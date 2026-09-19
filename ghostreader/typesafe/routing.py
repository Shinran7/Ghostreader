"""Toggle resolution and confidence / Noul band routing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ghostreader.config import GhostreaderConfig

# Mid-band lower bound; upper bound is typesafe_noul_positive_threshold (config).
NOUL_MID_BAND_LOW = 0.35

_SEVERITY_BUCKET = {"concern": 0, "neutral": 1, "strength": 2}


def resolve_typesafe_enabled(
    cli_flag: bool | None, cfg: GhostreaderConfig
) -> bool:
    """CLI flag wins when not None; else config; else False."""
    if cli_flag is not None:
        return bool(cli_flag)
    return bool(cfg.typesafe_enabled)


def needs_choice_enrich(
    severity: str,
    confidence: float,
    *,
    confidence_floor: float = 0.55,
) -> bool:
    """True when concern or low Choice confidence needs narrow LLM enrich."""
    if severity == "concern":
        return True
    return confidence < confidence_floor


def noul_band(
    noul: float,
    *,
    positive_threshold: float = 0.65,
    mid_low: float = NOUL_MID_BAND_LOW,
) -> str:
    """Return ``positive``, ``mid``, or ``negative`` for a Noul probability."""
    if noul >= positive_threshold:
        return "positive"
    if noul >= mid_low:
        return "mid"
    return "negative"


def prioritization_sort_key(finding: dict[str, Any]) -> tuple[int, float, str]:
    """Total order: severity bucket, then -certainty, then dimension name."""
    severity = str(finding.get("severity", "neutral"))
    bucket = _SEVERITY_BUCKET.get(severity, 1)
    certainty = float(finding.get("_certainty", 0.0) or 0.0)
    dimension = str(finding.get("dimension", ""))
    return (bucket, -certainty, dimension)
