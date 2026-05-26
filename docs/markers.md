# Marker reference

`@pytest.mark.metrics(...)` accepts:

| kwarg | meaning |
|-------|---------|
| `handler`, `method` | scope assertions to one path / HTTP method |
| `p50_below`, `p99_below` | latency percentile < threshold (seconds) |
| `min_requests` | total request count >= N |
| `no_errors` | zero 5xx responses |
| `max_error_rate` | 5xx rate <= fraction (e.g. `0.01` = 1%) |
| `max_4xx_rate` | 4xx rate <= fraction |
| `warmup_rounds`, `warmup_url` | run N warmup requests first, excluded from the window |
