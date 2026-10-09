"""Executor for the real phase: one fresh Claude Code session per task.

Each session runs `claude -p` in the working copy with a fresh, empty HOME (no memory, no user
settings, no session persistence). Token usage is read from the CLI's stream-json output;
cost is computed from config/prices.toml. Acceptance tests are restored from the pristine
copy in acceptance/ before every evaluation.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .interfaces import TaskResult
from .real_metrics import run as run_tool
from .real_metrics import tool_env

DISALLOWED_TOOLS = "Agent,Task,WebSearch,WebFetch"
EVAL_TAIL = 4000


class BudgetExhausted(RuntimeError):
    pass


class UsageUnavailable(RuntimeError):
    pass


class InfraError(RuntimeError):
    """The session hit a usage or rate limit or an API error; its result is not usable."""


INFRA_PATTERN = re.compile(r"usage limit|rate.?limit|hit your limit|limit reached|quota|"
                           r"api error|overloaded|\b(429|500|502|503|529)\b", re.IGNORECASE)


def infra_error(session: dict) -> str | None:
    """Return a reason if the session ended on a limit or an API error, else None."""
    res = session.get("result") or {}
    if res.get("subtype") == "error_max_budget_usd":
        return None  # runaway guard: a normal forced stop
    text = str(res.get("result") or "")
    if res.get("is_error") and INFRA_PATTERN.search(text):
        return text[:300]
    if not res and INFRA_PATTERN.search(session.get("stderr") or ""):
        return (session.get("stderr") or "")[-300:]
    return None


class Ledger:
    """Append-only spend ledger shared by all processes (flock-protected)."""

    def __init__(self, path: Path, cap_usd: float):
        self.path = Path(path)
        self.cap = cap_usd
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def _locked(self, mode: str):
        f = open(self.path, mode, encoding="utf-8")
        fcntl.flock(f, fcntl.LOCK_EX)
        return f

    def total(self) -> float:
        with self._locked("r") as f:
            return sum(json.loads(line)["cost_usd"] for line in f if line.strip())

    def add(self, cost_usd: float, **meta) -> None:
        with self._locked("a") as f:
            f.write(json.dumps({"cost_usd": cost_usd, "t": time.time(), **meta}) + "\n")

    def check(self, next_guard_usd: float) -> None:
        spent = self.total()
        if spent + next_guard_usd > self.cap:
            raise BudgetExhausted(
                f"spent {spent:.2f} USD; next session may cost up to {next_guard_usd:.2f}; "
                f"cap {self.cap:.2f}")


class Workspace:
    """A working copy of the website: its own git repository, never committed upstream."""

    def __init__(self, path: Path, repo_root: Path, start_ref: str, acceptance_dir: Path):
        self.path = Path(path)
        self.repo_root = Path(repo_root)
        self.start_ref = start_ref
        self.acceptance_dir = Path(acceptance_dir)

    def git(self, *args: str, check: bool = True) -> str:
        env = tool_env()
        env.update(GIT_AUTHOR_NAME="harness", GIT_AUTHOR_EMAIL="harness@localhost",
                   GIT_COMMITTER_NAME="harness", GIT_COMMITTER_EMAIL="harness@localhost")
        res = subprocess.run(["git", *args], cwd=self.path, env=env, text=True,
                             capture_output=True)
        if check and res.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr}")
        return res.stdout.strip()

    def create(self) -> None:
        if self.path.exists():
            shutil.rmtree(self.path)
        self.path.mkdir(parents=True)
        archive = subprocess.run(["git", "archive", f"{self.start_ref}:site"],
                                 cwd=self.repo_root, capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", str(self.path)], input=archive.stdout, check=True)
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"start from {self.start_ref}")
        self.install()

    def install(self) -> None:
        res = run_tool(["npm", "ci", "--no-audit"], self.path, timeout=600)
        if res.returncode != 0:
            raise RuntimeError(f"npm ci failed in {self.path}: {res.stderr[-2000:]}")

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def changed_files(self) -> list[str]:
        out = self.git("status", "--porcelain")
        return [line[3:] for line in out.splitlines() if line.strip()]

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        if self.git("status", "--porcelain"):
            self.git("commit", "-q", "-m", message)

    def reset(self, ref: str = "HEAD") -> None:
        deps_changed = any(f in ("package.json", "package-lock.json")
                           for f in self.changed_files())
        before = self.head()
        self.git("reset", "-q", "--hard", ref)
        self.git("clean", "-q", "-fd")
        if deps_changed or before != self.head():
            self.install()

    def stage_acceptance(self, item_ids: list[str]) -> None:
        dest = self.path / "acceptance"
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir()
        shutil.copy2(self.acceptance_dir / "_helpers.js", dest / "_helpers.js")
        for item in item_ids:
            shutil.copy2(self.acceptance_dir / f"{item}.test.js", dest / f"{item}.test.js")


def _session_env(home: str) -> dict:
    env = {"PATH": os.environ["PATH"], "HOME": home, "IS_SANDBOX": "1", "LANG": "C.UTF-8",
           "CI": "1", "NO_UPDATE_NOTIFIER": "1"}
    for k in ("HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy"):
        if k in os.environ:
            env[k] = os.environ[k]
    env["NODE_EXTRA_CA_CERTS"] = os.environ.get("NODE_EXTRA_CA_CERTS", "/root/.ccr/ca-bundle.crt")
    env["SSL_CERT_FILE"] = os.environ.get("SSL_CERT_FILE", "/root/.ccr/ca-bundle.crt")
    return env


def run_session(prompt: str, cwd: Path, model: str, guard_usd: float, timeout_s: int,
                transcript: Path | None = None, effort: str | None = None) -> dict:
    """Run one fresh `claude -p` session and return its usage, read from stream-json."""
    home = tempfile.mkdtemp(prefix="agent-home-")
    cmd = ["claude", "-p", prompt, "--model", model, "--output-format", "stream-json",
           "--verbose", "--no-session-persistence", "--max-budget-usd", f"{guard_usd:.2f}",
           "--permission-mode", "bypassPermissions", "--strict-mcp-config",
           "--disallowedTools", DISALLOWED_TOOLS]
    if effort:
        cmd += ["--effort", effort]
    started = time.time()
    proc = subprocess.Popen(cmd, cwd=cwd, env=_session_env(home), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    lines: list[str] = []
    reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
    reader.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
    reader.join(timeout=20)
    stderr = proc.stderr.read() if proc.stderr else ""
    shutil.rmtree(home, ignore_errors=True)
    if transcript:
        transcript.parent.mkdir(parents=True, exist_ok=True)
        transcript.write_text("".join(lines), encoding="utf-8")

    results, per_message = [], {}
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "result":
            results.append(ev)
        elif ev.get("type") == "assistant":
            msg = ev.get("message") or {}
            if msg.get("usage") and msg.get("id"):
                per_message[msg["id"]] = (msg.get("model", model), msg["usage"])
    # A session that starts background tasks can emit several result events. Each one's
    # `usage` covers only its own turn; `modelUsage` and `total_cost_usd` are cumulative.
    return {"result": results[-1] if results else None, "results": results,
            "per_message": per_message, "timed_out": timed_out,
            "returncode": proc.returncode, "stderr": stderr[-2000:],
            "duration_s": time.time() - started}


def _split(usage: dict) -> dict:
    cc = usage.get("cache_creation") or {}
    total_cw = usage.get("cache_creation_input_tokens", 0) or 0
    cw5 = cc.get("ephemeral_5m_input_tokens")
    cw1 = cc.get("ephemeral_1h_input_tokens")
    if cw5 is None and cw1 is None:
        cw5, cw1 = 0, total_cw  # the CLI writes 1h cache entries
    return {"input": usage.get("input_tokens", 0) or 0, "cw5": cw5 or 0, "cw1": cw1 or 0,
            "read": usage.get("cache_read_input_tokens", 0) or 0,
            "output": usage.get("output_tokens", 0) or 0}


def usage_by_model(session: dict, default_model: str) -> dict[str, dict]:
    """Token counts per model for the whole session.

    Sums `usage` over all result events (each covers one turn) and checks the sum against the
    cumulative `modelUsage` of the last result. Falls back to per-message usage only when the
    session produced no result event (killed at the timeout); stream events can under-count
    output tokens, so such sessions are flagged in the log (forced_stop).
    """
    results = session.get("results") or ([session["result"]] if session.get("result") else [])
    results = [r for r in results if r.get("usage")]
    if results:
        res = results[-1]
        models = res.get("modelUsage") or {}
        if len(models) <= 1:
            name = next(iter(models), default_model)
            summed = {"input": 0, "cw5": 0, "cw1": 0, "read": 0, "output": 0}
            for r in results:
                for k, v in _split(r["usage"]).items():
                    summed[k] += v
            mu = models.get(name)
            if mu:
                expected = (mu.get("inputTokens", 0), mu.get("cacheReadInputTokens", 0),
                            mu.get("cacheCreationInputTokens", 0), mu.get("outputTokens", 0))
                got = (summed["input"], summed["read"], summed["cw5"] + summed["cw1"],
                       summed["output"])
                if expected != got:
                    # A session stopped by the budget guard reports only part of its last
                    # turn in `usage`. Use the cumulative modelUsage when the per-request
                    # usage in the stream confirms its input-side counts exactly.
                    stream = {"input": 0, "cw5": 0, "cw1": 0, "read": 0, "output": 0}
                    for mname, usage in session.get("per_message", {}).values():
                        if mname == name:
                            for k, v in _split(usage).items():
                                stream[k] += v
                    if (stream["input"], stream["read"], stream["cw5"] + stream["cw1"]) != expected[:3]:
                        raise UsageUnavailable(f"per-turn usage {got} does not add up to the "
                                               f"cumulative modelUsage {expected}")
                    cw = expected[2]
                    cw5 = round(cw * summed["cw5"] / (summed["cw5"] + summed["cw1"])) if (
                        summed["cw5"] + summed["cw1"]) else 0
                    return {name: {"input": expected[0], "cw5": cw5, "cw1": cw - cw5,
                                   "read": expected[1], "output": expected[3]}}
            return {name: summed}
        out = {}
        for name, mu in models.items():
            out[name] = {"input": mu.get("inputTokens", 0), "cw5": 0,
                         "cw1": mu.get("cacheCreationInputTokens", 0),
                         "read": mu.get("cacheReadInputTokens", 0),
                         "output": mu.get("outputTokens", 0)}
        return out
    out: dict[str, dict] = {}
    for name, usage in session["per_message"].values():
        acc = out.setdefault(name, {"input": 0, "cw5": 0, "cw1": 0, "read": 0, "output": 0})
        for k, v in _split(usage).items():
            acc[k] += v
    return out


def _cost(t: dict, p: dict) -> float:
    return (t["input"] * p["input"] + t["cw5"] * p["cache_write_5m"]
            + t["cw1"] * p["cache_write_1h"] + t["read"] * p["cache_read"]
            + t["output"] * p["output"]) / 1_000_000


def _tiered_cost(name: str, t: dict, p: dict, per_message: dict | None) -> float:
    """Price a model whose rate depends on the prompt length of each request.

    Requests are read from the per-message usage of the stream (input-side counts match the
    result totals exactly; output counts in the stream can be lower). Input-side tokens are
    priced per request. Output tokens are taken from the totals and split between the tiers
    in proportion to the per-message output counts.
    """
    limit = p["tier_prompt_tokens"]
    zero = {"input": 0, "cw5": 0, "cw1": 0, "read": 0, "output": 0}
    tiers = {"base": dict(zero), "above": dict(zero)}
    last = "base"
    for mname, usage in (per_message or {}).values():
        if mname != name:
            continue
        u = _split(usage)
        tier = "above" if u["input"] + u["cw5"] + u["cw1"] + u["read"] > limit else "base"
        for k, v in u.items():
            tiers[tier][k] += v
        last = tier
    if per_message is None or all(tiers[x][k] == 0 for x in tiers for k in zero):
        tiers = {"base": dict(t), "above": dict(zero)}  # no request-level data: base tier
    else:
        out_seen = tiers["base"]["output"] + tiers["above"]["output"]
        for x in tiers:
            share = tiers[x]["output"] / out_seen if out_seen else float(x == last)
            tiers[x]["output"] = t["output"] * share
    return _cost(tiers["base"], p) + _cost(tiers["above"], p["above_tier"])


def price(tokens_by_model: dict[str, dict], price_table: dict,
          per_message: dict | None = None, cli_costs: dict | None = None) -> float:
    """USD for the session. For a model priced by prompt length, the CLI's own per-model
    cost is used when available: it prices each request with its exact output count, which
    the stream does not report. Otherwise output is split between tiers by _tiered_cost."""
    cost = 0.0
    for name, t in tokens_by_model.items():
        if name not in price_table:
            raise UsageUnavailable(f"no price for model {name!r}; add it to config/prices.toml")
        p = price_table[name]
        if "tier_prompt_tokens" in p:
            cli = (cli_costs or {}).get(name)
            cost += float(cli) if cli is not None else _tiered_cost(name, t, p, per_message)
        else:
            cost += _cost(t, p)
    return cost


def cli_model_costs(session: dict) -> dict:
    res = session.get("result") or {}
    return {m: v.get("costUSD") for m, v in (res.get("modelUsage") or {}).items()}


class RealExecutor:
    def __init__(self, ws: Workspace, *, model: str, price_table: dict, prompts: dict,
                 specs: dict, ledger: Ledger, session_timeout_s: int, transcript_dir: Path,
                 accepted: list[str] | None = None, label: str = "", effort: str | None = None,
                 ledger_meta: dict | None = None):
        self.ws = ws
        self.model = model
        self.price_table = price_table
        self.prompts = prompts
        self.specs = specs
        self.ledger = ledger
        self.timeout = session_timeout_s
        self.transcript_dir = Path(transcript_dir)
        self.accepted = list(accepted or [])
        self.label = label
        self.effort = effort
        self.ledger_meta = dict(ledger_meta or {})
        self._pending = None
        self._last_eval = ""
        self._counter = 0

    # ---- prompts ----
    def _prompt(self, task_type: str, item: str | None, context: dict) -> str:
        if task_type in ("impl", "calib", "debug"):
            spec = self.specs[item]
            key = "impl" if context.get("debug_index", 0) == 0 else "debug"
            return self.prompts[key].format(item_id=item, title=spec["title"],
                                            description=spec["description"],
                                            evaluation=self._last_eval[-EVAL_TAIL:])
        agent = task_type[len("maint_"):]
        fired = {f[0]: f for f in context.get("trigger", [])}
        if agent == "security":
            return self.prompts[task_type].format(value=fired["vulns"][1])
        if agent == "tests":
            f = fired["coverage"]
            return self.prompts[task_type].format(baseline_pct=f"{f[2] * 100:.1f}%",
                                                  value_pct=f"{f[1] * 100:.1f}%")
        if agent == "refactor":
            lines = []
            if "dup_ratio" in fired:
                f = fired["dup_ratio"]
                lines.append(f"- duplicated-code ratio is {f[1] * 100:.1f}% "
                             f"(baseline {f[2] * 100:.1f}%)")
            if "max_file_lines" in fired:
                f = fired["max_file_lines"]
                lines.append(f"- the largest source file has {f[1]} non-blank lines "
                             f"(baseline {f[2]})")
            return self.prompts[task_type].format(details="\n".join(lines))
        if agent == "knowledge":
            f = fired["avg_input_tokens"]
            return self.prompts[task_type].format(baseline=f"{f[2]:,.0f}", value=f"{f[1]:,.0f}")
        raise ValueError(task_type)

    # ---- evaluation ----
    def _evaluate(self, items: list[str]) -> tuple[bool, str]:
        self.ws.stage_acceptance(items)
        parts, ok = [], True
        steps = [("npm run build", ["npm", "run", "build"]), ("npm test", ["npm", "test"])]
        if items:
            steps.append(('node --test "acceptance/*.test.js"',
                          ["node", "--test", "acceptance/*.test.js"]))
        for name, cmd in steps:
            res = run_tool(cmd, self.ws.path, timeout=600)
            if res.returncode != 0:
                ok = False
                parts.append(f"$ {name}  (exit {res.returncode})\n"
                             f"{(res.stdout + res.stderr)[-EVAL_TAIL:]}")
        return ok, "\n\n".join(parts) if parts else "all checks passed"

    # ---- Executor protocol ----
    def start(self, task_type: str, item: str | None) -> None:
        self._pending = (task_type, item, self.ws.head())
        self._last_eval = ""

    def run(self, task_type: str, item: str | None, debug_index: int, week: int,
            guard_usd: float, context: dict) -> TaskResult:
        self.ledger.check(guard_usd)
        if task_type in ("impl", "debug", "calib"):
            check_items = [*self.accepted, item] if task_type != "calib" else [item]
        else:
            check_items = list(self.accepted)
        self.ws.stage_acceptance(check_items)
        ctx = dict(context, debug_index=debug_index)
        prompt = self._prompt(task_type, item, ctx)
        self._counter += 1
        transcript = self.transcript_dir / f"{self.label}-w{week}-{self._counter:03d}-{task_type}-{item or ''}.jsonl"

        session = None
        for attempt in range(3):
            session = run_session(prompt, self.ws.path, self.model, guard_usd, self.timeout,
                                  transcript, self.effort)
            if session["result"] or session["per_message"]:
                break
            if infra_error(session):
                break
            time.sleep(30 * (attempt + 1))  # infrastructure failure before any model call
        res = session["result"] or {}
        reason = infra_error(session)
        if reason:
            try:
                tokens = usage_by_model(session, self.model)
                cost = price(tokens, self.price_table, session["per_message"],
                             cli_model_costs(session)) if tokens else 0.0
            except UsageUnavailable:
                cost = 0.0
            self.ledger.add(cost, label=self.label, week=week, task_type=task_type, item=item,
                            session_id=res.get("session_id"), infra=reason, **self.ledger_meta)
            raise InfraError(reason)
        try:
            tokens = usage_by_model(session, self.model)
            if not tokens:
                raise UsageUnavailable(f"session produced no usage data: {session['stderr']}")
        except UsageUnavailable as e:
            # the session was paid for: record the CLI's own cost before giving up
            self.ledger.add(float(res.get("total_cost_usd") or 0.0), label=self.label,
                            week=week, task_type=task_type, item=item,
                            session_id=res.get("session_id"), usage_error=str(e)[:300],
                            **self.ledger_meta)
            raise
        cost = price(tokens, self.price_table, session["per_message"], cli_model_costs(session))
        self.ledger.add(cost, label=self.label, week=week, task_type=task_type, item=item,
                        session_id=res.get("session_id"), **self.ledger_meta)
        accepted, output = self._evaluate(check_items)
        self._last_eval = output
        totals = {k: sum(t[k] for t in tokens.values()) for k in ("input", "cw5", "cw1", "read", "output")}
        forced = (res.get("subtype") == "error_max_budget_usd") or session["timed_out"]
        return TaskResult(
            input_tokens=totals["input"], cache_write_tokens=totals["cw5"] + totals["cw1"],
            cache_read_tokens=totals["read"], output_tokens=totals["output"], cost_usd=cost,
            accepted=accepted, forced_stop=forced, model=";".join(sorted(tokens)),
            session_id=res.get("session_id", ""), duration_s=session["duration_s"],
            extra={"cli_cost_usd": res.get("total_cost_usd"), "num_turns": res.get("num_turns"),
                   "subtype": res.get("subtype"), "timed_out": session["timed_out"],
                   "is_error": bool(res.get("is_error")), "result_text": str(res.get("result") or "")[:300],
                   "tokens_by_model": tokens})

    def finish(self, keep: bool) -> None:
        task_type, item, head = self._pending
        self._pending = None
        if keep and task_type != "calib":
            self.ws.commit(f"{task_type} {item or ''}".strip())
            if task_type == "impl":
                self.accepted.append(item)
        else:
            self.ws.reset(head)
