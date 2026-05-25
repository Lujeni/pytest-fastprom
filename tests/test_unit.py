"""Unit tests for pytest-fastprom internals — no FastAPI app required."""

from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

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


def test_parse_thresholds_percentage_and_absolute():
    """Both percentage and absolute specs parse into Thresholds."""
    assert parse_thresholds("p50:10%,p99:0.05s") == [
        Threshold("p50", "pct", 10.0),
        Threshold("p99", "abs", 0.05),
    ]


def test_parse_thresholds_skips_blanks():
    """Empty comma-separated parts are ignored."""
    assert parse_thresholds("p50:10%, ,") == [Threshold("p50", "pct", 10.0)]


def test_parse_thresholds_rejects_garbage():
    """An unparsable spec raises ValueError."""
    with pytest.raises(ValueError, match="Invalid threshold"):
        parse_thresholds("p50:fast")


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
    """A change breaks the threshold only past its limit."""
    threshold = Threshold("p50", kind, value)
    assert threshold_exceeded(threshold, baseline, current) is expected


def test_regression_failure_str_percentage():
    """A percentage failure renders its change and limit."""
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


def _run(nodeid: str, p50: float) -> MetricsRun:
    """A one-handler run with the given P50, for compare/save tests."""
    run = MetricsRun()
    run.records[nodeid] = TestRecord(
        nodeid=nodeid,
        handlers={
            "GET /": HandlerMetrics(p50=p50, p99=p50, requests_total=1, errors_5xx=0)
        },
    )
    return run


def test_compare_flags_regression():
    """A P50 increase past the threshold is reported."""
    failures = _run("t::a", 0.200).compare(
        _run("t::a", 0.100), [Threshold("p50", "pct", 10.0)]
    )
    assert len(failures) == 1
    assert failures[0].current_val == 0.200


def test_compare_ignores_unchanged():
    """A change within the threshold reports nothing."""
    failures = _run("t::a", 0.105).compare(
        _run("t::a", 0.100), [Threshold("p50", "pct", 10.0)]
    )
    assert failures == []


def test_save_and_load_roundtrip(tmp_path):
    """A saved run reloads with its handler metrics intact."""
    path = tmp_path / "base.json"
    _run("t::a", 0.123).save(path)
    loaded = MetricsRun.load(path)
    assert loaded.records["t::a"].handlers["GET /"].p50 == 0.123


def _registry_with_requests(count: int) -> CollectorRegistry:
    """A registry holding ``count`` GET 2xx requests to ``/``."""
    registry = CollectorRegistry()
    counter = Counter(
        "http_requests", "desc", ["method", "status", "handler"], registry=registry
    )
    for _ in range(count):
        counter.labels("GET", "2xx", "/").inc()
    return registry


def test_snapshot_requests_total_with_filters():
    """requests_total filters by handler and returns zero when nothing matches."""
    snapshot = MetricsSnapshot(_registry_with_requests(3))
    assert snapshot.requests_total(handler="/", method="GET", status="2xx") == 3.0
    assert snapshot.requests_total(handler="/missing") == 0.0


def test_snapshot_percentile_from_histogram():
    """The percentile is the upper bound of the bucket the samples land in."""
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
    """No histogram data yields infinity."""
    assert MetricsSnapshot(CollectorRegistry()).p99_seconds() == float("inf")


def test_snapshot_reset_excludes_prior_requests():
    """reset() makes only post-reset requests count."""
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
    """A percentile outside (0, 1] raises ValueError."""
    with pytest.raises(ValueError, match="p must be in"):
        MetricsSnapshot(CollectorRegistry()).percentile_seconds(1.5)


def _registry_with_statuses(**by_status: int) -> CollectorRegistry:
    """A registry with the given count of requests per status class."""
    registry = CollectorRegistry()
    counter = Counter(
        "http_requests", "desc", ["method", "status", "handler"], registry=registry
    )
    for status, count in by_status.items():
        for _ in range(count):
            counter.labels("GET", status, "/").inc()
    return registry


def test_error_rate_ratio():
    """error_rate is the matching-status fraction of total requests."""
    snapshot = MetricsSnapshot(_registry_with_statuses(**{"2xx": 9, "5xx": 1}))
    assert snapshot.error_rate(handler="/") == 0.1
    assert snapshot.error_rate(status="4xx", handler="/") == 0.0


def test_error_rate_no_traffic_is_zero():
    """A handler with no requests has a zero error rate."""
    assert MetricsSnapshot(CollectorRegistry()).error_rate(handler="/") == 0.0


def test_assert_error_rate_below_passes_and_fails():
    """assert_error_rate_below passes within budget and fails past it."""
    snapshot = MetricsSnapshot(_registry_with_statuses(**{"2xx": 99, "5xx": 1}))
    snapshot.assert_error_rate_below(0.05, handler="/")
    with pytest.raises(AssertionError, match="error rate"):
        snapshot.assert_error_rate_below(0.005, handler="/")


def _registry_with_custom_counter() -> CollectorRegistry:
    """A registry with a custom ``cache_hits`` counter split by region."""
    registry = CollectorRegistry()
    counter = Counter("cache_hits", "desc", ["region"], registry=registry)
    counter.labels("eu").inc(3)
    counter.labels("us").inc(2)
    return registry


def test_metric_value_subset_and_total():
    """metric_value sums all series, or filters by a label subset."""
    snapshot = MetricsSnapshot(_registry_with_custom_counter())
    assert snapshot.metric_value("cache_hits_total") == 5.0  # all labels summed
    assert snapshot.metric_value("cache_hits_total", labels={"region": "eu"}) == 3.0
    assert snapshot.metric_value("missing_total") == 0.0


def test_assert_metric_comparisons():
    """assert_metric enforces every supplied comparison."""
    snapshot = MetricsSnapshot(_registry_with_custom_counter())
    snapshot.assert_metric("cache_hits_total", at_least=5, at_most=5, equals=5)
    snapshot.assert_metric("cache_hits_total", labels={"region": "us"}, greater_than=1)
    with pytest.raises(AssertionError, match="expected >= 6"):
        snapshot.assert_metric("cache_hits_total", at_least=6)


def test_assert_metric_requires_a_bound():
    """assert_metric with no comparison raises ValueError."""
    snapshot = MetricsSnapshot(_registry_with_custom_counter())
    with pytest.raises(ValueError, match="needs one of"):
        snapshot.assert_metric("cache_hits_total")


def test_metric_value_reads_extra_registries():
    """metric_value finds metrics living in an extra registry."""
    isolated = CollectorRegistry()
    app_registry = CollectorRegistry()  # stands in for the global default
    Counter("jobs", "desc", registry=app_registry).inc(4)

    snapshot = MetricsSnapshot(isolated, extra_registries=[app_registry])
    assert snapshot.metric_value("jobs_total") == 4.0


def test_metric_value_delta_vs_absolute():
    """delta gives change since reset; delta=False gives the absolute value."""
    registry = CollectorRegistry()
    jobs = Counter("jobs", "desc", registry=registry)
    depth = Gauge("queue_depth", "desc", registry=registry)
    jobs.inc(5)
    depth.set(7)

    snapshot = MetricsSnapshot(registry)
    snapshot.reset()  # baseline: jobs_total=5, queue_depth=7
    jobs.inc(2)
    depth.set(9)

    assert snapshot.metric_value("jobs_total") == 2.0  # counter delta since reset
    assert snapshot.metric_value("queue_depth", delta=False) == 9.0  # gauge absolute
    assert snapshot.metric_value("queue_depth") == 2.0  # gauge change since reset


def test_http_methods_ignore_extra_registries():
    """The HTTP path stays isolated; only metric_value merges extra registries."""
    isolated = _registry_with_requests(2)
    leaky = _registry_with_requests(5)  # same metric on a second registry

    snapshot = MetricsSnapshot(isolated, extra_registries=[leaky])
    assert snapshot.requests_total(handler="/") == 2.0  # isolated only
    assert snapshot.metric_value("http_requests_total") == 7.0  # custom path merges


def test_machine_info_diff_ignores_volatile_keys():
    """machine_info_differences reports interpreter changes, not hostname noise."""
    from pytest_fastprom.environment import machine_info_differences

    base = {"python_version": "3.13.0", "system": "Linux", "node": "ci-1"}
    current = {"python_version": "3.14.0", "system": "Linux", "node": "ci-2"}
    diffs = machine_info_differences(base, current)
    assert diffs == {"python_version": ("3.13.0", "3.14.0")}  # node excluded


def test_save_records_machine_metadata(tmp_path):
    """A saved run records the machine it ran on."""
    path = tmp_path / "base.json"
    _run("t::a", 0.123).save(path)
    loaded = MetricsRun.load(path)
    assert "machine_info" in loaded.metadata
    assert loaded.metadata["machine_info"]["python_implementation"]
