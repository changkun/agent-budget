"""Metrics source for the real phase: measures a working copy of the website."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from .dupcheck import dup_ratio

SOURCE_EXTENSIONS = (".js", ".mjs", ".cjs", ".ts", ".css")
COVERAGE_LINE = re.compile(r"^#\s*all files\s*\|\s*([\d.]+)\s*\|", re.MULTILINE)


def tool_env() -> dict:
    """Environment for npm/node commands run by the harness itself."""
    keep = ("PATH", "HOME", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy",
            "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "LANG")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.setdefault("NODE_EXTRA_CA_CERTS", "/root/.ccr/ca-bundle.crt")
    env["CI"] = "1"
    env["NO_UPDATE_NOTIFIER"] = "1"
    env["npm_config_update_notifier"] = "false"
    env["npm_config_fund"] = "false"
    return env


def run(cmd: list[str], cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=cwd, env=tool_env(), text=True, capture_output=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(cmd, 124, e.stdout or "", (e.stderr or "") + "\nTIMEOUT")


def line_counts(src: Path) -> tuple[int, int]:
    total = biggest = 0
    for p in sorted(src.rglob("*")):
        if p.is_file() and p.suffix in SOURCE_EXTENSIONS:
            n = sum(1 for line in p.read_text(encoding="utf-8", errors="replace").splitlines()
                    if line.strip())
            total += n
            biggest = max(biggest, n)
    return total, biggest


def coverage(workdir: Path) -> tuple[float | None, bool, str]:
    res = run(["npm", "run", "coverage"], workdir, timeout=600)
    out = res.stdout + res.stderr
    m = COVERAGE_LINE.search(out)
    return (float(m.group(1)) / 100 if m else None), res.returncode == 0, out


def vulnerabilities(workdir: Path) -> int | None:
    res = run(["npm", "audit", "--json"], workdir, timeout=180)
    try:
        data = json.loads(res.stdout)
        return int(data["metadata"]["vulnerabilities"]["total"])
    except (ValueError, KeyError, TypeError):
        return None


def outdated(workdir: Path) -> int | None:
    res = run(["npm", "outdated", "--json"], workdir, timeout=180)
    try:
        return len(json.loads(res.stdout or "{}"))
    except ValueError:
        return None


class RealMetrics:
    def __init__(self, workdir: Path):
        self.workdir = Path(workdir)

    def begin_week(self, week: int) -> None:
        pass

    def measure(self) -> dict:
        src = self.workdir / "src"
        loc, biggest = line_counts(src)
        build = run(["npm", "run", "build"], self.workdir, timeout=300)
        cov, tests_ok, _ = coverage(self.workdir)
        return {
            "loc": loc,
            "max_file_lines": biggest,
            "dup_ratio": round(dup_ratio(src)["dup_ratio"], 6),
            "coverage": None if cov is None else round(cov, 6),
            "vulns": vulnerabilities(self.workdir),
            "outdated_deps": outdated(self.workdir),
            "build_ok": int(build.returncode == 0),
            "tests_ok": int(tests_ok),
        }
