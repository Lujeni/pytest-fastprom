"""pytest-fastprom — isolated Prometheus metric assertions for FastAPI tests.

Install (auto-loads via the ``pytest11`` entry point)::

    pip install -e .

Marker — ``@pytest.mark.metrics(...)`` accepts:
    handler, method        scope assertions to one path / HTTP method
    p50_below, p99_below   assert latency percentile < threshold (seconds)
    min_requests           assert total request count >= N
    no_errors              assert zero 5xx responses
    max_error_rate         assert 5xx rate <= fraction (e.g. 0.01 = 1%)
    max_4xx_rate           assert 4xx rate <= fraction
    warmup_rounds          run N warmup requests before the measurement window
    warmup_url             URL used for auto warmup (default: "/")

CLI flags:
    --metrics-save=NAME          save this run to .pytest-metrics/NAME.json
    --metrics-compare=NAME       compare against a saved run
    --metrics-compare-fail=EXPR  thresholds, e.g. 'p50:10%,p99:20%' or 'p50:0.05s'
"""

from __future__ import annotations

# Fixtures must be importable from the plugin module so pytest discovers them.
from .fixtures import instrumented_client, metrics, metrics_registry
from .marker import check_metrics_marker
from .plugin import MetricsPytestPlugin, pytest_addoption, pytest_configure
from .regression import RegressionFailure, Threshold, parse_thresholds
from .snapshot import MetricsSnapshot
from .storage import HandlerMetrics, MetricsRun, TestRecord

__all__ = [
    # pytest hooks / fixtures
    "pytest_addoption",
    "pytest_configure",
    "metrics_registry",
    "instrumented_client",
    "metrics",
    # public API
    "MetricsSnapshot",
    "MetricsRun",
    "HandlerMetrics",
    "TestRecord",
    "Threshold",
    "RegressionFailure",
    "parse_thresholds",
    "check_metrics_marker",
    "MetricsPytestPlugin",
]
