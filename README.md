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

## Features

- **Prometheus-native**. Asserts on real histogram metrics, not stopwatch timing.
- **Isolated** registry per test. No metric leaks between tests.
- **SLO assertions** on P50, P99, request counts, and error rates.
- **Custom metrics**. `assert_metric` checks any Counter/Gauge/Histogram your app exposes.
- **Error budgets**. `max_error_rate` / `max_4xx_rate` assert a ratio, not just a zero count.
- **Regression detection**. Save a baseline, fail the build when it drifts.
- **Environment-aware baselines**. Saved runs record git commit + machine info and warn on cross-machine comparisons.
- **Warmup** support. Cold starts stay out of your measurement window.

## Install

```bash
uv add --dev pytest-fastprom
# or
pip install pytest-fastprom
```

## Docs

Full guide, marker reference, and regression detection: <https://github.com/lujeni/pytest-fastprom>.
