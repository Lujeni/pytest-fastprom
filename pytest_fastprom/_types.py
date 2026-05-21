"""Shared type aliases and Prometheus metric names."""

from __future__ import annotations

from typing import Final, TypeAlias

import pytest
from prometheus_client import CollectorRegistry

# A single sample identified by its name and frozen label set.
SampleKey: TypeAlias = tuple[str, frozenset[tuple[str, str]]]
SamplesDict: TypeAlias = dict[SampleKey, float]

METRIC_REQUESTS_TOTAL: Final = "http_requests_total"
METRIC_DURATION_BUCKET: Final = "http_request_duration_seconds_bucket"
METRIC_DURATION_COUNT: Final = "http_request_duration_seconds_count"

# Typed handles for per-test state shared across fixture, hook and snapshot.
REGISTRY_KEY: Final[pytest.StashKey[CollectorRegistry]] = pytest.StashKey()
BASELINE_KEY: Final[pytest.StashKey[SamplesDict]] = pytest.StashKey()
