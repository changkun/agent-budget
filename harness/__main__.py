"""Command line entry point.

    python3 -m harness sim [strong|weak|all]   run the simulated phase
    python3 -m harness dashboard               regenerate docs/index.html
    python3 -m harness report                  print summary tables (markdown)
    python3 -m harness methodology             regenerate docs/methodology.html
    python3 -m harness snapshot archive        bundle the real-run working copies
    python3 -m harness snapshot restore SERIES --dest DIR [--items K | --week W]
    python3 -m harness real calibrate          real phase: run calibration items
    python3 -m harness real run-all            real phase: run or resume all series
    python3 -m harness real run --group G --rep N
    python3 -m harness real status
    python3 -m harness capability prepare|feasibility|plan|run|status   (PLAN-capability.md)
"""
from __future__ import annotations

import argparse
import json
import sys

from . import config


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["capability"]:
        from . import capability
        return capability.main(argv[1:])
    ap = argparse.ArgumentParser(prog="harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_sim = sub.add_parser("sim")
    p_sim.add_argument("hypothesis", nargs="?", default="all",
                       choices=[*config.HYPOTHESES, "all"])
    p_sim.add_argument("--no-dashboard", action="store_true")
    sub.add_parser("dashboard")
    sub.add_parser("build-report")
    sub.add_parser("methodology")
    p_snap = sub.add_parser("snapshot")
    snap_sub = p_snap.add_subparsers(dest="snap_cmd", required=True)
    snap_sub.add_parser("archive")
    p_res = snap_sub.add_parser("restore")
    p_res.add_argument("series")
    p_res.add_argument("--dest", required=True)
    p_res.add_argument("--items", type=int, default=None)
    p_res.add_argument("--week", type=int, default=None)
    p_rep = sub.add_parser("report")
    p_rep.add_argument("--phase", default="sim")
    p_real = sub.add_parser("real")
    real_sub = p_real.add_subparsers(dest="real_cmd", required=True)
    p_cal = real_sub.add_parser("calibrate")
    p_cal.add_argument("--force", action="store_true")
    p_run = real_sub.add_parser("run")
    p_run.add_argument("--group", required=True)
    p_run.add_argument("--rep", type=int, required=True)
    p_run.add_argument("--deadline-min", type=float, default=95)
    p_all = real_sub.add_parser("run-all")
    p_all.add_argument("--parallel", type=int, default=None)
    p_all.add_argument("--deadline-min", type=float, default=95)
    real_sub.add_parser("status")
    args = ap.parse_args(argv)

    if args.cmd == "sim":
        from . import sim_run
        hyps = config.HYPOTHESES if args.hypothesis == "all" else [args.hypothesis]
        for h in hyps:
            meta = sim_run.run(h)
            plan = meta["plan"]
            print(f"sim {h}: budget={plan['budget']:.3f} cap={plan['cap']:.3f} "
                  f"calib_mean={plan['calib_mean']:.3f}")
        if not args.no_dashboard:
            from . import dashboard
            print(dashboard.build())
    elif args.cmd == "snapshot":
        from pathlib import Path
        from . import real_run, snapshots
        if args.snap_cmd == "archive":
            print(snapshots.archive(real_run.work_root()))
        else:
            print(snapshots.restore(args.series, Path(args.dest), args.items, args.week))
    elif args.cmd == "methodology":
        from . import methodology
        print(methodology.build())
    elif args.cmd == "build-report":
        from . import report
        print(report.build())
    elif args.cmd == "dashboard":
        from . import dashboard
        print(dashboard.build())
    elif args.cmd == "real":
        from . import real_run
        if args.real_cmd == "calibrate":
            meta = real_run.cmd_calibrate(force=args.force)
            plan, est = meta["plan"], meta["estimate"]
            print(json.dumps({"calib_costs": plan["calib_costs"], "calib_mean": plan["calib_mean"],
                              "budget": plan["budget"], "cap": plan["cap"],
                              "baseline": plan["baseline"], "estimate": est}, indent=2))
        elif args.real_cmd == "run":
            return real_run.cmd_run(args.group, args.rep, args.deadline_min)
        elif args.real_cmd == "run-all":
            parallel = args.parallel or real_run.settings()["parallel"]
            return real_run.cmd_run_all(parallel, args.deadline_min)
        elif args.real_cmd == "status":
            print(real_run.cmd_status())
    elif args.cmd == "report":
        from . import stats
        print(stats.markdown_summary(args.phase))
    return 0


if __name__ == "__main__":
    sys.exit(main())
