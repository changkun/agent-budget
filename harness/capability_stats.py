"""Estimates for the capability experiment (PLAN-capability.md sections 6 and 7).

A probe job is one probe task on one code state by one consumer: an implementation
session plus up to two debug sessions. Its cost is the sum of its sessions; it succeeds if
the last session passed evaluation. Cost to success on a set of probe jobs is total cost
divided by the number of successes, so failures count as spend without output.

Premium of consumer C on producer P's debt at k items, against maintainer X:

    pi = CTS(C on R) / CTS(C on M_X) - 1,   beta = pi / k

Intervals: 90% percentile bootstrap over (rep, probe) pairs; a pair contributes its R job
and its M job together. Maintenance cost m: mean over the maintenance jobs of that cell,
resampled by rep in the same bootstrap.
"""
from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from statistics import fmean

from .capability import DATA, parse_state, settings
from .logs import read_csv

BOOT = 2000
SEED = 11
QLO, QHI = 0.05, 0.95


def _q(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    if not xs:
        return math.nan
    return xs[min(len(xs) - 1, max(0, int(q * len(xs))))]


def load() -> dict:
    sessions = [r for r in read_csv(DATA / "sessions.csv") if r["block"] != "feas"]
    states = {r["state"]: r for r in read_csv(DATA / "states.csv")}
    probes: dict[str, dict] = {}
    maint: dict[str, dict] = {}
    produce: dict[tuple, dict] = {}
    for r in sessions:
        cost = float(r["cost_usd"])
        if r["kind"] == "probe":
            j = probes.setdefault(r["job"], {"model": r["model"], "state": r["state"],
                                             "item": r["item"], "cost": 0.0, "sessions": 0,
                                             "first_pass": None, "success": False,
                                             "output": 0, "input_total": 0})
            j["cost"] += cost
            j["sessions"] += 1
            j["output"] += int(r["output_tokens"])
            j["input_total"] += (int(r["input_tokens"]) + int(r["cache_write_tokens"])
                                 + int(r["cache_read_tokens"]))
            if r["task_type"] == "impl":
                j["first_pass"] = r["accepted"] == "1"
            j["success"] = r["accepted"] == "1"
        elif r["kind"] == "maint":
            j = maint.setdefault(r["job"], {"model": r["model"], "state": r["state"],
                                            "cost": 0.0, "kept": [], "ran": []})
            j["cost"] += cost
            j["ran"].append(r["task_type"])
            if r["accepted"] == "1":
                j["kept"].append(r["task_type"])
        elif r["kind"] == "produce":
            key = (r["model"], int(r["rep"]), r["item"])
            j = produce.setdefault(key, {"model": r["model"], "rep": int(r["rep"]),
                                         "item": r["item"], "k": int(r["k"]), "cost": 0.0,
                                         "sessions": 0, "first_pass": None, "success": False})
            j["cost"] += cost
            j["sessions"] += 1
            if r["task_type"] == "impl":
                j["first_pass"] = r["accepted"] == "1"
            j["success"] = r["accepted"] == "1"
    return {"probes": probes, "maint": maint, "produce": produce, "states": states}


def _cts(jobs: list[dict]) -> float:
    ok = sum(j["success"] for j in jobs)
    return sum(j["cost"] for j in jobs) / ok if ok else math.inf


def _probe_index(probes: dict) -> dict:
    """(consumer, state, rep, item) -> job; rep taken from the state id."""
    out = {}
    for j in probes.values():
        out[(j["model"], j["state"], j["item"])] = j
    return out


def premium(d: dict, consumer: str, producer: str, k: int, maintainer: str) -> dict | None:
    """Premium of `consumer` on `producer`'s R states against M_<maintainer>, pooled over reps."""
    idx = _probe_index(d["probes"])
    pairs = []
    for rep in settings()["reps"]:
        r_state = f"{producer}-r{rep}-k{k}-R"
        m_state = f"{producer}-r{rep}-k{k}-M{maintainer}"
        for p in settings()["probes"]:
            a, b = idx.get((consumer, r_state, p)), idx.get((consumer, m_state, p))
            if a and b:
                pairs.append((rep, a, b))
    if not pairs:
        return None
    # maintenance cost per rep from states.csv (0 when no maintenance agent fired)
    mjobs = defaultdict(list)
    for rep in settings()["reps"]:
        row = d["states"].get(f"{producer}-r{rep}-k{k}-M{maintainer}")
        if row:
            mjobs[rep].append(float(row["maint_cost_usd"] or 0.0))
    reps = sorted({p[0] for p in pairs})

    def stats(sample, mreps):
        r_cts = _cts([a for _, a, _ in sample])
        m_cts = _cts([b for _, _, b in sample])
        pi = r_cts / m_cts - 1 if math.isfinite(r_cts) and math.isfinite(m_cts) else math.nan
        m = fmean(c for rep in mreps for c in mjobs.get(rep, [])) if any(
            mjobs.get(rep) for rep in mreps) else math.nan
        mc = m / m_cts if math.isfinite(m_cts) and m == m else math.nan
        beta = pi / k
        nstar = math.sqrt(4 * mc / beta) if beta > 0 and mc == mc else math.inf
        return pi, beta, mc, nstar, r_cts, m_cts, m

    point = stats(pairs, reps)
    rng = random.Random(f"{SEED}:{consumer}:{producer}:{k}:{maintainer}")
    boots = []
    for _ in range(BOOT):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        mreps = [reps[rng.randrange(len(reps))] for _ in reps]
        boots.append(stats(sample, mreps))
    col = lambda i: [b[i] for b in boots if b[i] == b[i]]  # noqa: E731 - drop NaN
    pis, betas, ncol = col(0), col(1), [b[3] for b in boots]
    return {
        "consumer": consumer, "producer": producer, "k": k, "maintainer": maintainer,
        "pairs": len(pairs), "reps": len(reps),
        "pi": point[0], "pi_lo": _q(pis, QLO), "pi_hi": _q(pis, QHI),
        "beta": point[1], "beta_lo": _q(betas, QLO), "beta_hi": _q(betas, QHI),
        "m_over_c0": point[2], "nstar": point[3],
        "nstar_lo": _q(ncol, QLO), "nstar_hi": _q(ncol, QHI),
        "cts_r": point[4], "cts_m": point[5], "m": point[6],
        "success_r": fmean(a["success"] for _, a, _ in pairs),
        "success_m": fmean(b["success"] for _, _, b in pairs),
        "first_pass_r": fmean(bool(a["first_pass"]) for _, a, _ in pairs),
        "first_pass_m": fmean(bool(b["first_pass"]) for _, _, b in pairs),
    }


def capability(d: dict, model: str) -> dict:
    """Capability indicators of a model: probes on v0, and its own production run."""
    v0 = [j for j in d["probes"].values() if j["model"] == model and j["state"] == "v0"]
    allp = [j for j in d["probes"].values() if j["model"] == model]
    prod = [j for j in d["produce"].values() if j["model"] == model]
    out = {"model": model, "v0_jobs": len(v0), "c0_v0": _cts(v0) if v0 else None,
           "v0_first_pass": fmean(bool(j["first_pass"]) for j in v0) if v0 else None,
           "probe_jobs": len(allp),
           "probe_first_pass": fmean(bool(j["first_pass"]) for j in allp) if allp else None,
           "probe_success": fmean(j["success"] for j in allp) if allp else None}
    if prod:
        out.update(produce_items=len(prod), produce_accepted=sum(j["success"] for j in prod),
                   produce_first_pass=fmean(bool(j["first_pass"]) for j in prod),
                   produce_cost_per_item=fmean(j["cost"] for j in prod))
        xs = [j["k"] for j in prod]
        ys = [j["cost"] for j in prod]
        mx, my = fmean(xs), fmean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
        out["produce_cost_slope_rel"] = slope / (my - slope * mx) if my - slope * mx else None
    return out


def debt_growth(d: dict, producer: str, k: int) -> dict | None:
    """Mean change per item of the debt metrics from v0 to the producer's R states."""
    v0 = d["states"].get("v0")
    rows = [r for s, r in d["states"].items() if s.startswith(f"{producer}-") and s.endswith(f"-k{k}-R")]
    if not v0 or not rows:
        return None
    out = {"producer": producer, "k": k, "reps": len(rows),
           "n_accepted": fmean(int(r["n_accepted"]) for r in rows)}
    for key in ("loc", "max_file_lines", "dup_ratio", "coverage"):
        vals = [float(r[key]) for r in rows if r[key] != ""]
        if vals:
            out[key] = fmean(vals)
            out[f"{key}_per_item"] = (fmean(vals) - float(v0[key])) / k
    return out


def summarize() -> dict:
    s = settings()
    d = load()
    names = s["models"]
    ref = names[s["reference"]]
    consumers = [names[m] for m in s["models"]]
    producers = [ref] + [names[m] for m in s["models"] if names[m] != ref]
    out = {"capability": [capability(d, c) for c in consumers if any(
        j["model"] == c for j in d["probes"].values())]}
    e1, e2 = [], []
    for c in consumers:
        for k in s["sonnet_k"]:
            for maintainer, bucket in ((ref, e1), (c, e2)):
                est = premium(d, c, ref, k, maintainer)
                if est and not (bucket is e2 and c == ref):
                    bucket.append(est)
    out["E1_consumer_fixed_maintainer"] = e1
    out["E2_consumer_self_maintained"] = e2
    K = s["producer_k"]
    out["E3_producer_fixed_consumer"] = [x for x in (premium(d, ref, p, K, ref)
                                                    for p in producers if p != ref) if x]
    out["E3_debt_growth"] = [x for x in (debt_growth(d, p, K) for p in producers) if x] + \
        [x for x in (debt_growth(d, ref, k) for k in s["sonnet_k"]) if x]
    diag = [x for x in (premium(d, p, p, K, p) for p in producers if p != ref) if x]
    sonnet_self = premium(d, ref, ref, 29, ref)
    out["E4_diagonal"] = ([sonnet_self] if sonnet_self else []) + diag
    out["E5_matrix_sonnet_maintainer"] = [x for x in (
        premium(d, c, p, K if p != ref else 29, ref) for p in producers for c in consumers) if x]
    out["maintenance"] = maint_summary(d)
    return out


def maint_summary(d: dict) -> list[dict]:
    rows = defaultdict(list)
    for j in d["maint"].values():
        st = parse_state(j["state"])
        rows[(j["model"], st["producer"], st["k"])].append(j)
    out = []
    for (model, prod, k), js in sorted(rows.items()):
        out.append({"maintainer": model, "producer": prod, "k": k, "jobs": len(js),
                    "mean_cost": fmean(j["cost"] for j in js),
                    "sessions": sum(len(j["ran"]) for j in js),
                    "kept": sum(len(j["kept"]) for j in js)})
    return out


def write() -> str:
    out = summarize()
    (DATA / "summary.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
    return str(DATA / "summary.json")
