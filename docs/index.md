# pytest-fastprom

!!! danger "Proof of concept"
    This project is a proof of concept. The approach still needs real-world
    feedback (REX) before it can be considered validated, so treat results as a
    signal, not a guarantee. Most of the code was generated using generative AI.

## Why this project

`pytest-fastprom` started as a proof of concept around a specific blind spot: **performance regressions you can't see in a code review**.

The kind of change that looks harmless in a diff but quietly costs you milliseconds at runtime:

- an ORM relationship that now triggers an N+1 or a cache-busting join,
- a new middleware that runs on every request,
- an algorithm swapped for one with worse complexity on real-world input.

None of these break a test. None of them show up until latency creeps into production. The idea here is to **catch those drawbacks early**, right in the test suite, by reusing the measurement tool your app already trusts: **Prometheus**.

!!! warning "Not a load-testing tool"
This is **not** a replacement for real load testing. Reach for [k6](https://k6.io/) or [Locust](https://locust.io/) when you need concurrency, sustained throughput, or production-scale traffic.

    `pytest-fastprom` aims for something narrower and faster: a quick signal, on every test run, that a change didn't silently regress the latency or error budget you promised, measured with the same Prometheus histograms you already ship.

## Installation

```bash
uv add --dev pytest-fastprom
# or
pip install pytest-fastprom
```
