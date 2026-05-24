"""Machine and git metadata recorded alongside saved runs.

A saved baseline is only comparable to a run produced on a similar machine and,
usually, a known commit. We capture both at save time so :class:`MetricsRun`
can warn when a comparison crosses a meaningful environment boundary.
"""

from __future__ import annotations

import platform
import subprocess

# Keys whose change makes a latency comparison untrustworthy. Volatile fields
# (hostname, kernel release) are stored but deliberately excluded from the diff
# so routine CI noise does not trigger warnings.
_MACHINE_COMPARE_KEYS: tuple[str, ...] = (
    "python_implementation",
    "python_version",
    "system",
    "machine",
)


def collect_machine_info() -> dict[str, str]:
    """Describe the interpreter and host the run executed on."""
    return {
        "node": platform.node(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
    }


def collect_commit_info() -> dict[str, str | bool]:
    """Describe the current git commit, or ``{}`` outside a git work tree."""

    def git(*args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", *args],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0:
            return None
        return out.stdout.strip()

    commit_id = git("rev-parse", "HEAD")
    if commit_id is None:
        return {}

    info: dict[str, str | bool] = {"id": commit_id}
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch is not None:
        info["branch"] = branch
    status = git("status", "--porcelain")
    if status is not None:
        info["dirty"] = bool(status)
    return info


def machine_info_differences(
    baseline: dict[str, str], current: dict[str, str]
) -> dict[str, tuple[str, str]]:
    """Significant ``key -> (baseline, current)`` differences between two hosts.

    Only the keys in :data:`_MACHINE_COMPARE_KEYS` are considered, so a differing
    hostname or kernel release never raises a false alarm.
    """
    diffs: dict[str, tuple[str, str]] = {}
    for key in _MACHINE_COMPARE_KEYS:
        base_val = baseline.get(key, "")
        cur_val = current.get(key, "")
        if base_val != cur_val:
            diffs[key] = (base_val, cur_val)
    return diffs
