"""Archive and restore the real-run working copies as git bundles.

Each working copy is its own git repository with one commit per accepted backlog item or
maintenance run, so every intermediate state ("after k items") can be restored exactly.

    python3 -m harness snapshot archive            # bundles, manifest and logs into snapshots/
    python3 -m harness snapshot restore nomaint-r1 --items 20 --dest /tmp/x
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

from . import config, stats

SNAP_DIR = config.ROOT / "snapshots"
SERIES = [f"{g}-r{r}" for g in ("nomaint", "maint") for r in (1, 2, 3)]


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True,
                          check=True).stdout.strip()


def _manifest_for(series: str, repo: Path, runs: dict) -> dict:
    group, rep = series.split("-r")
    run = runs[(group, int(rep))]
    kept = [t for t in sorted(run["tasks"], key=lambda t: (t["week"], t["seq"]))
            if t["accepted"] and (t["task_type"] == "impl" or t["task_type"].startswith("maint_"))]
    log = _git(repo, "log", "--reverse", "--format=%H%x09%s").splitlines()
    commits = [line.split("\t", 1) for line in log]
    if len(commits) != len(kept) + 1:
        raise RuntimeError(f"{series}: {len(commits)} commits but {len(kept)} kept tasks + start")
    out = [{"sha": commits[0][0], "message": commits[0][1], "items": 0, "week": 0,
            "after": "start"}]
    items = 0
    for (sha, msg), t in zip(commits[1:], kept):
        expected = f"{t['task_type']} {t['item']}".strip()
        if msg != expected:
            raise RuntimeError(f"{series}: commit {sha[:8]} is {msg!r}, log says {expected!r}")
        if t["task_type"] == "impl":
            items += 1
        out.append({"sha": sha, "message": msg, "items": items, "week": t["week"],
                    "after": t["item"] or t["task_type"]})
    week_end = {}
    for c in out:
        week_end[c["week"]] = c["sha"]
    return {"series": series, "bundle": f"{series}.bundle", "commits": out,
            "week_end_commit": {str(w): sha for w, sha in sorted(week_end.items())}}


def _session_id(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            sid = json.loads(line).get("session_id")
        except ValueError:
            continue
        if sid:
            return sid
    return ""


def _archive_logs(work_root: Path) -> None:
    """Session transcripts and the spend ledger, with an index naming the run of each file."""
    data = config.ROOT / "docs" / "data" / "real"
    sessions = {}
    for run, path in (("invalid_maint_r2_first_run", data / "invalid/maint-r2-first-run/tasks.csv"),
                      ("valid", data / "real/tasks.csv")):
        for r in csv.DictReader(path.open()):
            if r["session_id"]:
                sessions[r["session_id"]] = run
    index = io.StringIO()
    w = csv.writer(index)
    w.writerow(["file", "session_id", "run"])
    files = sorted((work_root / "transcripts").glob("*.jsonl"))
    for f in files:
        sid = _session_id(f)
        w.writerow([f.name, sid, sessions.get(sid, "feasibility")])
    raw = index.getvalue().encode()
    with tarfile.open(SNAP_DIR / "logs.tar.xz", "w:xz") as tar:
        for f in files:
            tar.add(f, arcname=f"transcripts/{f.name}")
        info = tarfile.TarInfo("transcripts/index.csv")
        info.size = len(raw)
        tar.addfile(info, io.BytesIO(raw))
        tar.add(work_root / "ledger.jsonl", arcname="ledger.jsonl")


def archive(work_root: Path) -> str:
    SNAP_DIR.mkdir(exist_ok=True)
    runs = stats.runs_of(stats.load("real", "real"))
    manifest = {"start_ref": "site-v0", "series": []}
    for s in SERIES:
        repo = work_root / s
        bundle = SNAP_DIR / f"{s}.bundle"
        subprocess.run(["git", "bundle", "create", str(bundle), "--all"], cwd=repo,
                       capture_output=True, check=True)
        subprocess.run(["git", "bundle", "verify", str(bundle)], cwd=repo,
                       capture_output=True, check=True)
        manifest["series"].append(_manifest_for(s, repo, runs))
    (SNAP_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    _archive_logs(work_root)
    return f"archived {len(SERIES)} series into {SNAP_DIR.relative_to(config.ROOT)}/"


def restore(series: str, dest: Path, items: int | None = None, week: int | None = None) -> str:
    """Clone a series and check out the state after `items` accepted items or at a week's end."""
    manifest = json.loads((SNAP_DIR / "manifest.json").read_text())
    entry = next(e for e in manifest["series"] if e["series"] == series)
    if week is not None:
        sha = entry["week_end_commit"][str(week)]
    else:
        target = entry["commits"][-1]["items"] if items is None else items
        # last commit with that many items (includes any maintenance done right after)
        sha = [c for c in entry["commits"] if c["items"] <= target][-1]["sha"]
    if dest.exists():
        shutil.rmtree(dest)
    subprocess.run(["git", "clone", "-q", str(SNAP_DIR / entry["bundle"]), str(dest)], check=True)
    subprocess.run(["git", "checkout", "-q", sha], cwd=dest, check=True)
    return f"{series} at {sha[:8]} -> {dest}"
