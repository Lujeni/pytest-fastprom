# pytest-fastprom

**Turn your SLOs into pytest assertions.**

Smoketest your FastAPI against the latency and error budgets you actually promised. Built on the Prometheus metrics your app already exposes, not wall-clock `timeit` guesses.

```python
def test_home_meets_slo(instrumented_client, metrics):
    instrumented_client.get("/")
    metrics.assert_p99_below(1.0, handler="/")
    metrics.assert_no_server_errors()
```

Or declare the SLO right on the test:

```python
@pytest.mark.metrics(p99_below=1.0, min_requests=3, no_errors=True)
def test_route_within_budget(instrumented_client):
    for _ in range(3):
        instrumented_client.get("/")
```

Spend an **error budget** instead of demanding zero failures:

```python
@pytest.mark.metrics(handler="/checkout", max_error_rate=0.01, max_4xx_rate=0.05)
def test_checkout_stays_in_budget(instrumented_client):
    for _ in range(100):
        instrumented_client.post("/checkout")
    # passes while 5xx ≤ 1% and 4xx ≤ 5% of requests
```

Assert on **your own metrics**, not just the built-in HTTP ones. Declare them
the ordinary way — a module-level `Counter` on the default registry — and assert
without any wiring:

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

## Features

- 📊 **Prometheus-native**. Asserts on real histogram metrics, not stopwatch timing.
- 🔬 **Isolated** registry per test. No metric leaks between tests.
- 🎯 **SLO assertions** on P50, P99, request counts, and error rates.
- 🧩 **Custom metrics**. `assert_metric` checks any Counter/Gauge/Histogram your app exposes.
- 💸 **Error budgets**. `max_error_rate` / `max_4xx_rate` assert a ratio, not just a zero count.
- 📉 **Regression detection**. Save a baseline, fail the build when it drifts.
- 🖥️ **Environment-aware baselines**. Saved runs record git commit + machine info; comparing against a baseline from a different interpreter or arch warns you.
- 🔥 **Warmup** support. Cold starts stay out of your measurement window.

## Marker reference

`@pytest.mark.metrics(...)` accepts:

| kwarg | meaning |
|-------|---------|
| `handler`, `method` | scope assertions to one path / HTTP method |
| `p50_below`, `p99_below` | latency percentile < threshold (seconds) |
| `min_requests` | total request count ≥ N |
| `no_errors` | zero 5xx responses |
| `max_error_rate` | 5xx rate ≤ fraction (e.g. `0.01` = 1%) |
| `max_4xx_rate` | 4xx rate ≤ fraction |
| `warmup_rounds`, `warmup_url` | run N warmup requests first, excluded from the window |

## Regression detection

```bash
# record a baseline (stores metrics + git commit + machine info)
pytest --metrics-save=main

# later, fail the build if latency drifts past the threshold
pytest --metrics-compare=main --metrics-compare-fail='p50:10%,p99:20%'
```

When the baseline was recorded on a different interpreter or architecture, the
comparison still runs but prints a warning so you don't trust a cross-machine
delta.
