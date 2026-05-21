"""Regression thresholds and the failures they produce."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

_PERCENT_RE = re.compile(r"^(p\d+):(\d+(?:\.\d+)?)%$")
_ABSOLUTE_RE = re.compile(r"^(p\d+):(\d+(?:\.\d+)?)s$")


@dataclass(frozen=True, slots=True)
class Threshold:
    """One regression rule: which metric, how to compare, and the limit."""

    metric: str  # "p50" or "p99"
    kind: Literal["pct", "abs"]  # percentage increase, or absolute seconds
    value: float  # 10.0 means +10%, 0.05 means +50ms


@dataclass(slots=True)
class RegressionFailure:
    """A single threshold violation for one metric/handler/test."""

    nodeid: str
    handler: str
    metric: str
    baseline_val: float
    current_val: float
    threshold: Threshold

    def __str__(self) -> str:
        metric = self.metric.upper()
        base, current = self.baseline_val, self.current_val
        prefix = (
            f"  {self.nodeid}  [{self.handler}]  {metric}: {base:.3f}s → {current:.3f}s"
        )
        if self.threshold.kind == "pct":
            change = (current - base) / base * 100
            return f"{prefix}  (+{change:.1f}%, limit: +{self.threshold.value:.0f}%)"
        diff = current - base
        return f"{prefix}  (+{diff:.3f}s, limit: +{self.threshold.value:.3f}s)"


def parse_thresholds(spec: str) -> list[Threshold]:
    """Parse a comma-separated threshold spec.

    Each part is either ``p50:10%`` (max percentage increase) or ``p50:0.05s``
    (max absolute increase). Example: ``"p50:10%,p99:20%"``.
    """
    thresholds: list[Threshold] = []
    for raw in spec.split(","):
        part = raw.strip()
        if not part:
            continue
        if match := _PERCENT_RE.match(part):
            thresholds.append(Threshold(match.group(1), "pct", float(match.group(2))))
        elif match := _ABSOLUTE_RE.match(part):
            thresholds.append(Threshold(match.group(1), "abs", float(match.group(2))))
        else:
            raise ValueError(
                f"Invalid threshold: {part!r}. "
                "Use 'p50:10%' (percentage) or 'p50:0.05s' (absolute)."
            )
    return thresholds


def threshold_exceeded(
    threshold: Threshold, baseline_val: float, current_val: float
) -> bool:
    """Whether the change from ``baseline_val`` to ``current_val`` breaks the rule."""
    if threshold.kind == "pct":
        return (current_val - baseline_val) / baseline_val * 100 > threshold.value
    return (current_val - baseline_val) > threshold.value
