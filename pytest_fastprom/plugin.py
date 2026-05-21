"""Pytest plugin: option registration, marker checks and the session report."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest
from _pytest.terminal import TerminalReporter

from ._types import REGISTRY_KEY
from .marker import check_metrics_marker
from .regression import RegressionFailure, parse_thresholds
from .snapshot import MetricsSnapshot
from .storage import MetricsRun

_STORAGE_DIRNAME = ".pytest-metrics"
_DEFAULT_FAIL_SPEC = "p50:20%,p99:20%"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the ``--metrics-*`` command line options."""
    group = parser.getgroup("metrics", "FastAPI Prometheus metrics")
    group.addoption(
        "--metrics-save",
        metavar="NAME",
        default=None,
        help=f"Save this run's metrics as NAME in {_STORAGE_DIRNAME}/",
    )
    group.addoption(
        "--metrics-compare",
        metavar="NAME",
        default=None,
        help="Compare against saved baseline NAME",
    )
    group.addoption(
        "--metrics-compare-fail",
        metavar="EXPR",
        default=_DEFAULT_FAIL_SPEC,
        help=(
            "Regression thresholds: 'p50:10%%,p99:20%%' (percentage) "
            f"or 'p50:0.05s' (absolute seconds). Default: {_DEFAULT_FAIL_SPEC}"
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register the marker and the stateful plugin instance."""
    config.addinivalue_line(
        "markers",
        "metrics(p50_below=, p99_below=, min_requests=, no_errors=, "
        "handler=, method=, warmup_rounds=, warmup_url='/'): "
        "auto-assert Prometheus metrics after test; optional warmup window",
    )
    config.pluginmanager.register(MetricsPytestPlugin(config), MetricsPytestPlugin.NAME)


class MetricsPytestPlugin:
    """Collects per-test metrics, runs regression checks and prints the report."""

    NAME = "_metrics_plugin"

    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        self.run = MetricsRun()
        self._regression_failures: list[RegressionFailure] = []
        self._missing_baseline: str | None = None

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_call(self, item: pytest.Item) -> Generator[None, None, None]:
        """Evaluate ``@pytest.mark.metrics`` after the test body has run."""
        result = yield  # let the test (and any failure) run first

        registry = item.stash.get(REGISTRY_KEY, None)
        marker = item.get_closest_marker("metrics")
        if registry is not None and marker is not None:
            check_metrics_marker(marker, MetricsSnapshot(registry, node=item))
        return result

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        """Persist the run and/or detect regressions against a baseline."""
        storage_dir = Path(self.config.rootpath) / _STORAGE_DIRNAME

        save_name: str | None = self.config.getoption("--metrics-save", default=None)
        if save_name:
            self.run.save(storage_dir / f"{save_name}.json")

        compare_name: str | None = self.config.getoption(
            "--metrics-compare", default=None
        )
        if not compare_name:
            return

        baseline_path = storage_dir / f"{compare_name}.json"
        if not baseline_path.exists():
            self._missing_baseline = str(baseline_path)
            return

        baseline = MetricsRun.load(baseline_path)
        fail_spec: str = self.config.getoption(
            "--metrics-compare-fail", default=_DEFAULT_FAIL_SPEC
        )
        self._regression_failures = self.run.compare(
            baseline, parse_thresholds(fail_spec)
        )
        if self._regression_failures:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(
        self,
        terminalreporter: TerminalReporter,
        exitstatus: int,
        config: pytest.Config,
    ) -> None:
        """Print the metrics table and the regression verdict."""
        self.run.print_table(terminalreporter)

        save_name: str | None = config.getoption("--metrics-save", default=None)
        if save_name:
            terminalreporter.write_sep(
                "-", f"metrics saved → {_STORAGE_DIRNAME}/{save_name}.json"
            )

        compare_name: str | None = config.getoption("--metrics-compare", default=None)
        if not compare_name:
            return

        if self._missing_baseline:
            terminalreporter.write_sep(
                "!",
                f"metrics baseline not found: {self._missing_baseline}",
                yellow=True,
            )
        elif self._regression_failures:
            terminalreporter.write_sep("=", "METRICS REGRESSIONS", red=True)
            for failure in self._regression_failures:
                terminalreporter.write_line(str(failure), red=True)
        else:
            terminalreporter.write_sep(
                "-", f"metrics compare OK vs '{compare_name}'", green=True
            )
