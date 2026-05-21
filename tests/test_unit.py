"""Unit tests for pytest-fastprom internals — no FastAPI app required."""

from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry, Counter, Histogram

from pytest_fastprom import (
    HandlerMetrics,
    MetricsRun,
    MetricsSnapshot,
    RegressionFailure,
    TestRecord,
    Threshold,
    parse_thresholds,
)
from pytest_fastprom.regression import threshold_exceeded


# --- parse_thresholds -------------------------------------------------------


def test_parse_thresholds_percentage_and_absolute():
    assert parse_thresholds("p50:10%,p99:0.05s") == [
        Threshold("p50", "pct", 10.0),
        Threshold("p99", "abs", 0.05),
    ]


def test_parse_thresholds_skips_blanks():
    assert parse_thresholds("p50:10%, ,") == [Threshold("p50", "pct", 10.0)]


def test_parse_thresholds_rejects_garbage():
    with pytest.raises(ValueError, match="Invalid threshold"):
        parse_thresholds("p50:fast")


# --- threshold_exceeded -----------------------------------------------------


@pytest.mark.parametrize(
    "kind, value, baseline, current, expected",
    [
        ("pct", 10.0, 0.100, 0.115, True),  # +15% > 10%
        ("pct", 10.0, 0.100, 0.105, False),  # +5% < 10%
        ("abs", 0.05, 0.100, 0.160, True),  # +60ms > 50ms
        ("abs", 0.05, 0.100, 0.140, False),  # +40ms < 50ms
    ],
)
def test_threshold_exceeded(kind, value, baseline, current, expected):
    threshold = Threshold("p50", kind, value)
    assert threshold_exceeded(threshold, baseline, current) is expected


# --- RegressionFailure.__str__ ----------------------------------------------


def test_regression_failure_str_percentage():
    failure = RegressionFailure(
        nodeid="t::a",
        handler="GET /",
        metric="p50",
        baseline_val=0.100,
        current_val=0.150,
        threshold=Threshold("p50", "pct", 10.0),
    )
    text = str(failure)
    assert "+50.0%" in text and "limit: +10%" in text


# --- MetricsRun.compare -----------------------------------------------------


def _run(nodeid: str, p50: float) -> MetricsRun:
    run = MetricsRun()
    run.records[nodeid] = TestRecord(
        nodeid=nodeid,
        handlers={
            "GET /": HandlerMetrics(p50=p50, p99=p50, requests_total=1, errors_5xx=0)
        },
    )
    return run


def test_compare_flags_regression():
    failures = _run("t::a", 0.200).compare(
        _run("t::a", 0.100), [Threshold("p50", "pct", 10.0)]
    )
    assert len(failures) == 1
    assert failures[0].current_val == 0.200


def test_compare_ignores_unchanged():
    failures = _run("t::a", 0.105).compare(
        _run("t::a", 0.100), [Threshold("p50", "pct", 10.0)]
    )
    assert failures == []


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "base.json"
    _run("t::a", 0.123).save(path)
    loaded = MetricsRun.load(path)
    assert loaded.records["t::a"].handlers["GET /"].p50 == 0.123


# --- MetricsSnapshot (registry built by hand, no FastAPI) -------------------


def _registry_with_requests(count: int) -> CollectorRegistry:
    registry = CollectorRegistry()
    counter = Counter(
        "http_requests", "desc", ["method", "status", "handler"], registry=registry
    )
    for _ in range(count):
        counter.labels("GET", "2xx", "/").inc()
    return registry


def test_snapshot_requests_total_with_filters():
    snapshot = MetricsSnapshot(_registry_with_requests(3))
    assert snapshot.requests_total(handler="/", method="GET", status="2xx") == 3.0
    assert snapshot.requests_total(handler="/missing") == 0.0


def test_snapshot_percentile_from_histogram():
    registry = CollectorRegistry()
    hist = Histogram(
        "http_request_duration_seconds",
        "desc",
        ["method", "handler"],
        buckets=(0.1, 0.5, 1.0),
        registry=registry,
    )
    for _ in range(10):
        hist.labels("GET", "/").observe(0.3)  # lands in the 0.5 bucket

    snapshot = MetricsSnapshot(registry)
    assert snapshot.p50_seconds(handler="/", method="GET") == 0.5


def test_snapshot_percentile_empty_is_inf():
    assert MetricsSnapshot(CollectorRegistry()).p99_seconds() == float("inf")


def test_snapshot_reset_excludes_prior_requests():
    registry = CollectorRegistry()
    counter = Counter(
        "http_requests", "desc", ["method", "status", "handler"], registry=registry
    )
    counter.labels("GET", "2xx", "/").inc(3)

    snapshot = MetricsSnapshot(registry)
    snapshot.reset()  # baseline = 3 requests, only later ones count

    counter.labels("GET", "2xx", "/").inc(2)
    assert snapshot.requests_total(handler="/") == 2.0


def test_percentile_rejects_bad_p():
    with pytest.raises(ValueError, match="p must be in"):
        MetricsSnapshot(CollectorRegistry()).percentile_seconds(1.5)
