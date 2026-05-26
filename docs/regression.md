# Regression detection

```bash
# record a baseline (stores metrics + git commit + machine info)
pytest --metrics-save=main

# later, fail the build if latency drifts past the threshold
pytest --metrics-compare=main --metrics-compare-fail='p50:10%,p99:20%'
```

When the baseline was recorded on a different interpreter or architecture, the
comparison still runs but prints a warning so you don't trust a cross-machine
delta.
