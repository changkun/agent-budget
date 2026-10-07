# agent-budget

An experiment on how a coding agent should split a fixed weekly budget between
maintenance and implementation.

Two groups work through the same 40-item backlog on the same codebase with the same
weekly budget:

- **nomaint**: the whole budget goes to implementation (plus up to two debug sessions per item).
- **maint**: each week starts by measuring the codebase; every metric past its threshold
  triggers the matching maintenance agent; the rest of the budget goes to implementation.

Questions: does the per-item implementation cost of `nomaint` rise week over week, and does
`maint` deliver more items over 8 weeks?

The plan (in Chinese) is in [PLAN.md](PLAN.md); the final report will be in `REPORT.md`.

## Phases

1. **Simulation** (no model calls). A seeded model of codebase state and task cost, run under
   two coefficient sets: `strong` (a worse codebase clearly raises cost and failure rate) and
   `weak` (it barely matters). All coefficients are assumptions and live in `config/sim/`.
   Simulated results show how the conclusion depends on the assumptions; they cannot show
   whether the premise is true.
2. **Real run**. The same loop drives fresh Claude Code sessions (`claude -p`) against a small
   website generated in `site/`. Same log format, same dashboard.

## Layout

```
config/            experiment rules, thresholds, prices, simulation coefficients
harness/           scheduling loop, executors, metrics sources, stats, dashboard builder
tests/             unit tests for the loop rules
docs/index.html    dashboard (single self-contained file, regenerated after every run)
docs/data/         raw logs: <phase>/<hypothesis>/{tasks,weeks,metrics}.csv and run.json
site/              website used in the real run
backlog/           backlog items and calibration items for the real run
acceptance/        acceptance tests, kept outside the working copies
```

Working copies for the real run live outside the repository (`/home/user/agent-work`, see
`config/real.toml`) and are never committed; only logs and end-of-week metrics are.

## Usage

Python 3.11+ standard library only.

```sh
python3 -m harness sim all        # run both simulated hypotheses and rebuild the dashboard
python3 -m harness dashboard      # rebuild docs/index.html from docs/data/
python3 -m harness report         # print summary tables
python3 -m unittest discover -s tests

python3 -m harness real calibrate # real phase: 6 calibration tasks, budget and cap
python3 -m harness real run-all   # real phase: all series (resumable at week boundaries)
python3 -m harness real status
python3 -m harness build-report   # regenerate REPORT.md tables from docs/report_template.md
```

Open `docs/index.html` directly in a browser, or serve `docs/` with GitHub Pages.

## Rules in short

- A "week" is a fixed budget, not calendar time; 8 weeks; unused budget expires.
- Weekly budget = 4.5 × mean calibration item cost; item cap = 1.5 × 80th percentile of
  calibration item cost.
- A new item starts only if the remaining budget is at least one item cap. A session always
  runs to completion; cost above the cap is recorded as overspend and no further debug session
  starts. A negative week balance is deducted from the next week's budget.
- Up to two debug sessions after a failed acceptance check; then the item is rolled back and
  counted as failed.
- Maintenance triggers are relative to the week-0 baseline (`config/thresholds.toml`).
