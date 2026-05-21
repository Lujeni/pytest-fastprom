"""SLO-as-code for the items API."""

import pytest


@pytest.mark.metrics(
    handler="/items/{item_id}",
    p99_below=0.25,  # SLO: P99 < 250ms (histogram bucket granularity)
    min_requests=10,
    no_errors=True,
    warmup_rounds=2,
)
def test_items_read_slo(instrumented_client):
    for i in (1, 2):
        for _ in range(5):
            r = instrumented_client.get(f"/items/{i}")
            assert r.status_code == 200


def test_search_is_slow_inline(instrumented_client, metrics):
    """Inline-style assertion — useful when SLO depends on test body logic."""
    for _ in range(4):
        assert instrumented_client.get("/search").status_code == 200

    p99 = metrics.p99_seconds(handler="/search")
    assert p99 >= 0.25, f"expected /search slow path, got P99={p99}s"
    metrics.assert_no_server_errors()


@pytest.mark.metrics(handler="/items/{item_id}", no_errors=True, min_requests=1)
def test_missing_item_returns_404_not_500(instrumented_client):
    """404 is a 4xx — does not trip no_errors (which only catches 5xx)."""
    r = instrumented_client.get("/items/999")
    assert r.status_code == 404
