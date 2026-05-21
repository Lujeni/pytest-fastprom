"""Pytest fixtures exposed to user tests."""

from __future__ import annotations

from typing import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry
from prometheus_fastapi_instrumentator import Instrumentator

from ._types import BASELINE_KEY, REGISTRY_KEY
from .plugin import MetricsPytestPlugin
from .snapshot import MetricsSnapshot, collect_samples


@pytest.fixture
def metrics_registry() -> CollectorRegistry:
    """A fresh, isolated registry per test — no global Prometheus state leaks."""
    return CollectorRegistry()


@pytest.fixture
def instrumented_client(
    request: pytest.FixtureRequest,
    fastapi_app: FastAPI,
    metrics_registry: CollectorRegistry,
) -> Generator[TestClient, None, None]:
    """A ``TestClient`` for an app instrumented with the isolated registry.

    Requires a ``fastapi_app`` fixture in your ``conftest.py``. When the test
    carries ``@pytest.mark.metrics(warmup_rounds=N)``, N warmup requests run
    first and are excluded from later assertions. On teardown the snapshot is
    recorded in the session run for the table, ``--metrics-save`` and compare.
    """
    # Shared with the hook and metrics.reset() via the node's typed stash.
    request.node.stash[REGISTRY_KEY] = metrics_registry

    Instrumentator(registry=metrics_registry).instrument(fastapi_app)

    with TestClient(fastapi_app) as client:
        marker = request.node.get_closest_marker("metrics")
        if marker is not None and marker.kwargs.get("warmup_rounds", 0) > 0:
            warmup_url: str = marker.kwargs.get("warmup_url", "/")
            for _ in range(marker.kwargs["warmup_rounds"]):
                client.get(warmup_url)
            # Everything so far becomes the baseline; only later requests count.
            request.node.stash[BASELINE_KEY] = collect_samples(metrics_registry)

        yield client

    snapshot = MetricsSnapshot(metrics_registry, node=request.node)
    plugin: MetricsPytestPlugin | None = request.config.pluginmanager.get_plugin(
        MetricsPytestPlugin.NAME
    )
    if plugin is not None:
        plugin.run.record(request.node.nodeid, snapshot)


@pytest.fixture
def metrics(
    request: pytest.FixtureRequest,
    metrics_registry: CollectorRegistry,
) -> MetricsSnapshot:
    """A live snapshot for inline assertions inside the test body.

    Shares the baseline with :func:`instrumented_client` through the node, so
    calling ``metrics.reset()`` starts a manual warmup window.
    """
    return MetricsSnapshot(metrics_registry, node=request.node)
