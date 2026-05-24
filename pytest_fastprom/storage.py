"""Per-test metric records: collect, persist, load, and compare across runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from _pytest.terminal import TerminalReporter

from .environment import collect_commit_info, collect_machine_info
from .regression import RegressionFailure, Threshold, threshold_exceeded
from .snapshot import MetricsSnapshot

_NO_DATA = -1.0  # stored P50/P99 when the histogram had no samples


@dataclass(slots=True)
class HandlerMetrics:
    """Latency and traffic for one handler/method combination."""

    p50: float  # seconds, or -1.0 when no histogram data
    p99: float  # seconds, or -1.0 when no histogram data
    requests_total: float
    errors_5xx: float


@dataclass(slots=True)
class TestRecord:
    """Every handler measured during a single test, keyed by ``"METHOD /path"``."""

    nodeid: str
    handlers: dict[str, HandlerMetrics] = field(default_factory=dict)

    __test__ = False  # not a pytest test class despite the "Test" prefix


class MetricsRun:
    """All :class:`TestRecord` collected over one pytest session."""

    def __init__(self) -> None:
        self.records: dict[str, TestRecord] = {}
        # Populated on save and on load; empty for an in-memory run.
        self.metadata: dict = {}

    def record(self, nodeid: str, snapshot: MetricsSnapshot) -> None:
        """Extract per-handler metrics from a finished test's snapshot."""
        record = TestRecord(nodeid=nodeid)
        for method, handler in sorted(snapshot.seen_handlers()):
            p50 = snapshot.p50_seconds(method=method, handler=handler)
            p99 = snapshot.p99_seconds(method=method, handler=handler)
            record.handlers[f"{method} {handler}"] = HandlerMetrics(
                p50=p50 if p50 != float("inf") else _NO_DATA,
                p99=p99 if p99 != float("inf") else _NO_DATA,
                requests_total=snapshot.requests_total(method=method, handler=handler),
                errors_5xx=snapshot.requests_total(status="5xx", handler=handler),
            )
        if record.handlers:
            self.records[nodeid] = record

    def save(self, path: Path) -> None:
        """Write this run to ``path`` as JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata: dict = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "machine_info": collect_machine_info(),
        }
        commit_info = collect_commit_info()
        if commit_info:
            metadata["commit_info"] = commit_info
        self.metadata = metadata
        payload = {
            "metadata": metadata,
            "tests": {
                nodeid: {
                    "handlers": {key: asdict(hm) for key, hm in rec.handlers.items()}
                }
                for nodeid, rec in self.records.items()
            },
        }
        path.write_text(json.dumps(payload, indent=2))

    @classmethod
    def load(cls, path: Path) -> MetricsRun:
        """Read a previously saved run from ``path``."""
        run = cls()
        payload = json.loads(path.read_text())
        run.metadata = payload.get("metadata", {})
        for nodeid, test_data in payload.get("tests", {}).items():
            record = TestRecord(nodeid=nodeid)
            for key, hm_data in test_data.get("handlers", {}).items():
                record.handlers[key] = HandlerMetrics(**hm_data)
            run.records[nodeid] = record
        return run

    def compare(
        self, baseline: MetricsRun, thresholds: list[Threshold]
    ) -> list[RegressionFailure]:
        """Return every threshold violation between this run and ``baseline``."""
        failures: list[RegressionFailure] = []
        for nodeid, current_rec in self.records.items():
            baseline_rec = baseline.records.get(nodeid)
            if baseline_rec is None:
                continue
            for handler_key, current_hm in current_rec.handlers.items():
                baseline_hm = baseline_rec.handlers.get(handler_key)
                if baseline_hm is None:
                    continue
                for threshold in thresholds:
                    current_val = getattr(current_hm, threshold.metric, None)
                    baseline_val = getattr(baseline_hm, threshold.metric, None)
                    if (
                        current_val is None
                        or baseline_val is None
                        or baseline_val <= 0.0
                    ):
                        continue
                    if threshold_exceeded(threshold, baseline_val, current_val):
                        failures.append(
                            RegressionFailure(
                                nodeid=nodeid,
                                handler=handler_key,
                                metric=threshold.metric,
                                baseline_val=baseline_val,
                                current_val=current_val,
                                threshold=threshold,
                            )
                        )
        return failures

    def print_table(self, reporter: TerminalReporter) -> None:
        """Print a per-handler summary table to the terminal reporter."""
        if not self.records:
            return
        widths = {"test": 40, "handler": 28, "p50": 8, "p99": 8, "reqs": 6, "err": 6}
        header = (
            f"{'TEST':<{widths['test']}}  {'HANDLER':<{widths['handler']}}"
            f"  {'P50':>{widths['p50']}}  {'P99':>{widths['p99']}}"
            f"  {'REQS':>{widths['reqs']}}  {'ERR':>{widths['err']}}"
        )
        reporter.write_sep("-", "METRICS REPORT")
        reporter.line(header)
        reporter.line("-" * len(header))
        for nodeid, record in sorted(self.records.items()):
            short = nodeid.split("::")[-1]
            for handler_key, hm in sorted(record.handlers.items()):
                p50 = f"{hm.p50:.3f}s" if hm.p50 >= 0.0 else "n/a"
                p99 = f"{hm.p99:.3f}s" if hm.p99 >= 0.0 else "n/a"
                reporter.line(
                    f"{short:<{widths['test']}}  {handler_key:<{widths['handler']}}"
                    f"  {p50:>{widths['p50']}}  {p99:>{widths['p99']}}"
                    f"  {hm.requests_total:>{widths['reqs']}.0f}"
                    f"  {hm.errors_5xx:>{widths['err']}.0f}"
                )
