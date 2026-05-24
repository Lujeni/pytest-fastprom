"""Live, baseline-aware view over an isolated Prometheus registry."""

from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry

from ._types import (
    BASELINE_KEY,
    METRIC_DURATION_BUCKET,
    METRIC_DURATION_COUNT,
    METRIC_REQUESTS_TOTAL,
    SampleKey,
    SamplesDict,
)


def collect_samples(registry: CollectorRegistry) -> SamplesDict:
    """Flatten every sample in a registry into a {(name, labels): value} dict."""
    samples: SamplesDict = {}
    for metric in registry.collect():
        for sample in metric.samples:
            key: SampleKey = (sample.name, frozenset(sample.labels.items()))
            samples[key] = sample.value
    return samples


class MetricsSnapshot:
    """Read and assert on metrics from a single test's registry.

    Registries start empty per test, so raw values already equal the per-test
    delta. After :meth:`reset` (or marker-driven warmup) a baseline is stored on
    the pytest item and subtracted, so only requests made afterwards count.
    """

    def __init__(
        self,
        registry: CollectorRegistry,
        node: pytest.Item | None = None,
        preset_baseline: SamplesDict | None = None,
    ) -> None:
        self._registry = registry
        # Baseline lives on the node so the fixture, hook and reset() all share it.
        self._node = node
        # Used only for node-less snapshots (e.g. session recording).
        self._preset_baseline = preset_baseline

    def _get_baseline(self) -> SamplesDict | None:
        if self._node is not None:
            return self._node.stash.get(BASELINE_KEY, None)
        return self._preset_baseline

    def _samples(self) -> SamplesDict:
        """Current samples, as a delta from the baseline when one is set."""
        raw = collect_samples(self._registry)
        baseline = self._get_baseline()
        if baseline is None:
            return raw
        return {
            key: value - baseline.get(key, 0.0)
            for key, value in raw.items()
            if value - baseline.get(key, 0.0) > 0.0
        }

    def seen_handlers(self) -> set[tuple[str, str]]:
        """All (method, handler) pairs present in the current samples."""
        seen: set[tuple[str, str]] = set()
        for (name, labels_frozen), _ in self._samples().items():
            if name != METRIC_REQUESTS_TOTAL:
                continue
            labels = dict(labels_frozen)
            handler = labels.get("handler", "")
            if handler:
                seen.add((labels.get("method", "GET"), handler))
        return seen

    def reset(self) -> None:
        """Mark the current state as the measurement start.

        Subsequent assertions count only requests made after this call, which
        makes it easy to exclude manual warmup requests::

            for _ in range(3):
                client.get("/items/1")  # warmup, not counted
            metrics.reset()
            client.get("/items/1")      # counted
            metrics.assert_p50_below(0.5)
        """
        baseline = collect_samples(self._registry)
        if self._node is not None:
            self._node.stash[BASELINE_KEY] = baseline
        else:
            self._preset_baseline = baseline

    def get(self, sample_name: str, labels: dict[str, str] | None = None) -> float:
        """Value for one exact sample name and label combination."""
        key: SampleKey = (sample_name, frozenset((labels or {}).items()))
        return self._samples().get(key, 0.0)

    def requests_total(
        self,
        *,
        method: str | None = None,
        status: str | None = None,
        handler: str | None = None,
    ) -> float:
        """Sum of ``http_requests_total`` matching the given filters.

        ``status`` is the instrumentator grouping: ``"2xx"``..``"5xx"``.
        """
        total = 0.0
        for (name, labels_frozen), value in self._samples().items():
            if name != METRIC_REQUESTS_TOTAL:
                continue
            labels = dict(labels_frozen)
            if method and labels.get("method") != method.upper():
                continue
            if status and labels.get("status") != status:
                continue
            if handler and labels.get("handler") != handler:
                continue
            total += value
        return total

    def error_rate(
        self,
        *,
        status: str = "5xx",
        method: str | None = None,
        handler: str | None = None,
    ) -> float:
        """Fraction of matching requests whose status class is ``status``.

        Returns ``0.0`` when no requests match — a route with no traffic cannot
        exceed an error budget. ``status`` is the instrumentator grouping, e.g.
        ``"5xx"`` for server errors or ``"4xx"`` for client errors.
        """
        total = self.requests_total(method=method, handler=handler)
        if total == 0.0:
            return 0.0
        errors = self.requests_total(method=method, status=status, handler=handler)
        return errors / total

    def percentile_seconds(
        self,
        p: float,
        *,
        method: str | None = None,
        handler: str | None = None,
    ) -> float:
        """Approximate the Pn latency from the duration histogram.

        Returns the upper bound of the first bucket whose cumulative count
        reaches ``p * total``, or ``inf`` when there is no histogram data.
        """
        if not 0.0 < p <= 1.0:
            raise ValueError(f"p must be in (0, 1], got {p}")

        samples = self._samples()

        def matches(labels: dict[str, str]) -> bool:
            if method and labels.get("method") != method.upper():
                return False
            if handler and labels.get("handler") != handler:
                return False
            return True

        total_count = sum(
            value
            for (name, labels_frozen), value in samples.items()
            if name == METRIC_DURATION_COUNT and matches(dict(labels_frozen))
        )
        if total_count == 0.0:
            return float("inf")

        target = p * total_count
        bucket_sums: dict[float, float] = {}
        for (name, labels_frozen), value in samples.items():
            if name != METRIC_DURATION_BUCKET:
                continue
            labels = dict(labels_frozen)
            if not matches(labels):
                continue
            le_raw = labels.get("le", "+Inf")
            le = float("inf") if le_raw == "+Inf" else float(le_raw)
            bucket_sums[le] = bucket_sums.get(le, 0.0) + value

        for le, cumulative in sorted(bucket_sums.items()):
            if cumulative >= target:
                return le
        return float("inf")

    def p50_seconds(
        self, *, method: str | None = None, handler: str | None = None
    ) -> float:
        """Approximate median (P50) latency in seconds."""
        return self.percentile_seconds(0.50, method=method, handler=handler)

    def p99_seconds(
        self, *, method: str | None = None, handler: str | None = None
    ) -> float:
        """Approximate P99 latency in seconds."""
        return self.percentile_seconds(0.99, method=method, handler=handler)

    def assert_requests_total(
        self,
        *,
        method: str | None = None,
        status: str | None = None,
        handler: str | None = None,
        min_count: int = 1,
    ) -> None:
        """Assert at least ``min_count`` requests match the filters."""
        actual = self.requests_total(method=method, status=status, handler=handler)
        assert actual >= min_count, (
            f"Expected >= {min_count} requests "
            f"[method={method!r} status={status!r} handler={handler!r}], got {actual}"
        )

    def assert_no_server_errors(self) -> None:
        """Assert no 5xx responses were recorded."""
        count = self.requests_total(status="5xx")
        assert count == 0.0, f"Found {count:.0f} server error(s) (5xx)"

    def assert_error_rate_below(
        self,
        max_rate: float,
        *,
        status: str = "5xx",
        method: str | None = None,
        handler: str | None = None,
    ) -> None:
        """Assert the ``status`` error rate is at or below ``max_rate`` (0..1)."""
        rate = self.error_rate(status=status, method=method, handler=handler)
        assert rate <= max_rate, (
            f"{status} error rate {rate:.2%} exceeds budget {max_rate:.2%} "
            f"[method={method!r} handler={handler!r}]"
        )

    def assert_percentile_below(
        self,
        p: float,
        threshold_seconds: float,
        *,
        method: str | None = None,
        handler: str | None = None,
    ) -> None:
        """Assert the Pn latency is at or below ``threshold_seconds``."""
        actual = self.percentile_seconds(p, method=method, handler=handler)
        assert actual <= threshold_seconds, (
            f"P{int(p * 100)} latency {actual}s exceeds threshold "
            f"{threshold_seconds}s [method={method!r} handler={handler!r}]"
        )

    def assert_p50_below(
        self,
        threshold_seconds: float,
        *,
        method: str | None = None,
        handler: str | None = None,
    ) -> None:
        """Assert median (P50) latency is at or below ``threshold_seconds``."""
        self.assert_percentile_below(
            0.50, threshold_seconds, method=method, handler=handler
        )

    def assert_p99_below(
        self,
        threshold_seconds: float,
        *,
        method: str | None = None,
        handler: str | None = None,
    ) -> None:
        """Assert P99 latency is at or below ``threshold_seconds``."""
        self.assert_percentile_below(
            0.99, threshold_seconds, method=method, handler=handler
        )

    def dump(self) -> str:
        """Render all current samples as a debug string."""
        lines = [
            f"  {name}{dict(labels_frozen)} = {value}"
            for (name, labels_frozen), value in sorted(self._samples().items())
        ]
        return "\n".join(lines) if lines else "  (no metrics recorded)"
