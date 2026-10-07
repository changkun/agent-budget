"""Log formats shared by both phases. One CSV per kind, one directory per (phase, hypothesis)."""
from __future__ import annotations

import csv
import fcntl
import json
from pathlib import Path

TASK_COLUMNS = [
    "phase", "hypothesis", "group", "rep", "week", "seq", "item", "task_type", "debug_index",
    "input_tokens", "cache_write_tokens", "cache_read_tokens", "output_tokens",
    "total_input_tokens", "cost_usd", "accepted", "rolled_back", "item_cost_usd",
    "overspend_usd", "forced_stop", "trigger_metric", "trigger_value", "trigger_baseline",
    "trigger_threshold", "model", "session_id", "duration_s", "cli_cost_usd",
]

WEEK_COLUMNS = [
    "phase", "hypothesis", "group", "rep", "week", "budget_usd", "carryover_in_usd",
    "available_usd", "loc", "max_file_lines", "dup_ratio", "coverage", "vulns", "outdated_deps",
    "build_ok", "tests_ok", "avg_input_tokens", "spend_maint_security", "spend_maint_tests",
    "spend_maint_refactor", "spend_maint_knowledge", "spend_maint", "spend_impl", "spend_debug",
    "spend_implementation", "unused_usd", "week_overspend_usd", "predicted_items",
    "completed_items", "failed_items", "item_overspend_count", "item_overspend_usd",
    "triggered", "maint_skipped",
]

METRIC_COLUMNS = [
    "phase", "hypothesis", "group", "rep", "week", "point", "loc", "max_file_lines", "dup_ratio",
    "coverage", "vulns", "outdated_deps", "build_ok", "tests_ok", "avg_input_tokens",
]

FILES = {"tasks": TASK_COLUMNS, "weeks": WEEK_COLUMNS, "metrics": METRIC_COLUMNS}


def _fmt(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".") if value == value else ""
    return str(value)


class RunLog:
    """Appends rows to tasks.csv, weeks.csv and metrics.csv under one directory."""

    def __init__(self, directory: Path, fresh: bool = False):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        for name, columns in FILES.items():
            path = self.dir / f"{name}.csv"
            if fresh or not path.exists():
                with open(path, "w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(columns)

    def append(self, kind: str, row: dict) -> None:
        columns = FILES[kind]
        unknown = set(row) - set(columns)
        if unknown:
            raise KeyError(f"unknown {kind} columns: {sorted(unknown)}")
        with open(self.dir / f"{kind}.csv", "a", newline="", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)  # several run processes may append concurrently
            csv.writer(f).writerow([_fmt(row.get(c)) for c in columns])

    def write_run_meta(self, meta: dict) -> None:
        with open(self.dir / "run.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")


def drop_rows(directory: Path, group: str, rep: int, after_week: int) -> None:
    """Remove rows of one (group, rep) with week > after_week (an interrupted week)."""
    for name, columns in FILES.items():
        path = Path(directory) / f"{name}.csv"
        if not path.exists():
            continue
        with open(path, "r+", newline="", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            rows = list(csv.DictReader(f))
            keep = [r for r in rows if not (r["group"] == group and int(r["rep"]) == rep
                                            and int(r["week"]) > after_week)]
            f.seek(0)
            f.truncate()
            w = csv.writer(f)
            w.writerow(columns)
            for r in keep:
                w.writerow([r.get(c, "") for c in columns])


def read_csv(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
