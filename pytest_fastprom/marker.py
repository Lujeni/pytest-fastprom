"""Evaluation of the ``@pytest.mark.metrics`` marker."""

from __future__ import annotations

import pytest

from .snapshot import MetricsSnapshot


def _format_latency(value: float) -> str:
    return "no-data" if value == float("inf") else f"{value:.3f}s"


def check_metrics_marker(marker: pytest.Mark, snapshot: MetricsSnapshot) -> None:
    """Check the marker's kwargs against ``snapshot``.

    Calls :func:`pytest.fail` on any violation so the test reports as FAILED
    rather than ERROR. Supported kwargs: ``handler``, ``method``, ``p50_below``,
    ``p99_below``, ``min_requests`` and ``no_errors``.
    """
    kwargs = marker.kwargs
    handler: str | None = kwargs.get("handler")
    method: str | None = kwargs.get("method")
    scope = f"[handler={handler!r} method={method!r}]"
    violations: list[str] = []

    if "p50_below" in kwargs:
        p50 = snapshot.p50_seconds(method=method, handler=handler)
        limit: float = kwargs["p50_below"]
        if p50 > limit:
            violations.append(f"P50 {_format_latency(p50)} > {limit}s {scope}")

    if "p99_below" in kwargs:
        p99 = snapshot.p99_seconds(method=method, handler=handler)
        limit = kwargs["p99_below"]
        if p99 > limit:
            violations.append(f"P99 {_format_latency(p99)} > {limit}s {scope}")

    if "min_requests" in kwargs:
        actual = snapshot.requests_total(method=method, handler=handler)
        minimum: int = kwargs["min_requests"]
        if actual < minimum:
            violations.append(f"requests_total {actual:.0f} < {minimum} {scope}")

    if kwargs.get("no_errors", False):
        errors = snapshot.requests_total(status="5xx", handler=handler)
        if errors > 0.0:
            violations.append(f"found {errors:.0f} 5xx error(s) [handler={handler!r}]")

    if violations:
        pytest.fail(
            "@pytest.mark.metrics violations:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )
