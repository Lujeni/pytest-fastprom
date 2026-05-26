# Usage

## Assert against your SLO

Drive the app through `instrumented_client`, then assert on the `metrics` fixture:

```python
def test_home_meets_slo(instrumented_client, metrics):
    instrumented_client.get("/")
    metrics.assert_p99_below(1.0, handler="/")
    metrics.assert_no_server_errors()
```

## Declare the SLO on the test

The `metrics` marker checks the budget after the test body runs:

```python
@pytest.mark.metrics(p99_below=1.0, min_requests=3, no_errors=True)
def test_route_within_budget(instrumented_client):
    for _ in range(3):
        instrumented_client.get("/")
```

## Spend an error budget

Allow a ratio of failures instead of demanding zero:

```python
@pytest.mark.metrics(handler="/checkout", max_error_rate=0.01, max_4xx_rate=0.05)
def test_checkout_stays_in_budget(instrumented_client):
    for _ in range(100):
        instrumented_client.post("/checkout")
    # passes while 5xx <= 1% and 4xx <= 5% of requests
```

## Assert on your own metrics

Declare a metric the ordinary way (a module-level `Counter` on the default
registry) and assert without any wiring:

```python
# in your app
from prometheus_client import Counter
CACHE_HITS = Counter("cache_hits", "served from cache", ["region"])

# in your test
def test_cache_is_used(instrumented_client, metrics):
    instrumented_client.get("/items/1")
    metrics.assert_metric("cache_hits_total", at_least=1)          # this test's delta
    metrics.assert_metric("queue_depth", delta=False, at_most=10)  # gauge: absolute
```

`labels` is a subset filter (omit it to sum every series). Because the app's
global registry is shared across tests, counters report **this test's delta** by
default; pass `delta=False` for a gauge whose current value you want as-is.
