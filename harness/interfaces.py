"""The two replaceable parts of the scheduling loop: executor and metrics source."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

TASK_TYPES = ("calib", "impl", "debug",
              "maint_security", "maint_tests", "maint_refactor", "maint_knowledge")
METRIC_KEYS = ("loc", "max_file_lines", "dup_ratio", "coverage", "vulns", "outdated_deps",
               "build_ok", "tests_ok")


@dataclass
class TaskResult:
    input_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    output_tokens: int
    cost_usd: float
    accepted: bool
    forced_stop: bool = False
    model: str = ""
    session_id: str = ""
    duration_s: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def total_input_tokens(self) -> int:
        return self.input_tokens + self.cache_write_tokens + self.cache_read_tokens


class Executor(Protocol):
    def start(self, task_type: str, item: str | None) -> None:
        """Snapshot the workspace before a backlog item or maintenance task."""

    def run(self, task_type: str, item: str | None, debug_index: int, week: int,
            guard_usd: float, context: dict) -> TaskResult:
        """Run one agent session and evaluate it (acceptance or build+tests)."""

    def finish(self, keep: bool) -> None:
        """Keep the changes (commit) or roll back to the snapshot."""


class MetricsSource(Protocol):
    def begin_week(self, week: int) -> None:
        """Hook called at the start of each week (simulation injects random events)."""

    def measure(self) -> dict:
        """Return the current values for METRIC_KEYS."""
