"""Command line entry point.

    python3 -m harness sim [strong|weak|all]   run the simulated phase
    python3 -m harness dashboard               regenerate docs/index.html
    python3 -m harness report                  print summary tables (markdown)
"""
from __future__ import annotations

import argparse
import sys

from . import config


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_sim = sub.add_parser("sim")
    p_sim.add_argument("hypothesis", nargs="?", default="all",
                       choices=[*config.HYPOTHESES, "all"])
    p_sim.add_argument("--no-dashboard", action="store_true")
    sub.add_parser("dashboard")
    p_rep = sub.add_parser("report")
    p_rep.add_argument("--phase", default="sim")
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
    elif args.cmd == "dashboard":
        from . import dashboard
        print(dashboard.build())
    elif args.cmd == "report":
        from . import stats
        print(stats.markdown_summary(args.phase))
    return 0


if __name__ == "__main__":
    sys.exit(main())
