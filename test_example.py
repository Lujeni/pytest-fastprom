"""
Example tests — demonstrates inline assertions, markers, warmup, and regression detection.
"""

import pytest


def test_read_main(instrumented_client, metrics):
    """Inline assertions on request count and server errors."""
    response = instrumented_client.get("/")
    assert response.status_code == 200
    assert response.json() == {"msg": "Hello World"}
    metrics.assert_requests_total(handler="/", method="GET", status="2xx", min_count=1)
    metrics.assert_no_server_errors()


def test_p99_latency(instrumented_client, metrics):
    """Inline P99 latency assertion on a handler."""
    for _ in range(10):
        instrumented_client.get("/")
    metrics.assert_p99_below(1.0, handler="/", method="GET")


def test_multiple_routes_isolated(instrumented_client, metrics):
    """Each handler is counted independently within the test."""
    instrumented_client.get("/")
    instrumented_client.get("/items/42")
    metrics.assert_requests_total(handler="/", min_count=1)
    metrics.assert_requests_total(handler="/items/{item_id}", min_count=1)
    metrics.assert_requests_total(min_count=2)


@pytest.mark.metrics(p99_below=1.0, min_requests=3, no_errors=True)
def test_marker_fast_route(instrumented_client):
    """Marker checks P99 < 1s, >= 3 requests, zero errors — all pass."""
    for _ in range(3):
        instrumented_client.get("/")


@pytest.mark.metrics(
    handler="/items/{item_id}", method="GET", p99_below=1.0, min_requests=2
)
def test_marker_items_route(instrumented_client):
    """Marker scoped to a specific handler."""
    instrumented_client.get("/items/1")
    instrumented_client.get("/items/2")


@pytest.mark.metrics(handler="/", max_error_rate=0.0, min_requests=3)
def test_marker_error_budget(instrumented_client):
    """5xx error rate must stay within budget (0% here) — all 2xx, passes."""
    for _ in range(3):
        instrumented_client.get("/")


@pytest.mark.metrics(handler="/slow", p50_below=0.1, p99_below=0.2)
def test_marker_slow_fails(instrumented_client):
    """/slow sleeps 300ms → P50 = 0.5s bucket. p50_below=0.1 WILL FAIL."""
    for _ in range(5):
        instrumented_client.get("/slow")


@pytest.mark.metrics(warmup_rounds=3, warmup_url="/", p99_below=1.0, min_requests=5)
def test_auto_warmup(instrumented_client, metrics):
    """
    3 warmup requests to '/' are excluded from measurement.
    The 5 requests below are the only ones that count.
    """
    for _ in range(5):
        instrumented_client.get("/")

    # warmup requests NOT counted: exactly 5 in window
    assert metrics.requests_total(handler="/") == 5.0


def test_manual_warmup(instrumented_client, metrics):
    """
    metrics.reset() marks end of warmup window.
    Only post-reset requests appear in assertions.
    """
    for _ in range(3):
        instrumented_client.get("/")  # warmup — not counted
    metrics.reset()

    for _ in range(5):
        instrumented_client.get("/")  # measurement window

    # Exactly 5, not 8
    assert metrics.requests_total(handler="/") == 5.0
    metrics.assert_p99_below(1.0, handler="/")
    metrics.assert_requests_total(handler="/", min_count=5)


def test_slow_endpoint_median_threshold(instrumented_client, metrics):
    """/slow sleeps 300ms → bucket 0.5s. assert P50 < 0.1s WILL FAIL."""
    for _ in range(5):
        assert instrumented_client.get("/slow").status_code == 200

    p50 = metrics.p50_seconds(handler="/slow", method="GET")
    print(f"\nActual P50: {p50}s  (sleep=0.3s, bucket upper bound=0.5s)")
    metrics.assert_p50_below(0.1, handler="/slow", method="GET")
