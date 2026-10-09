# Real-run snapshots

The original rules kept the working copies out of the repository and committed only logs and
end-of-week metrics. After the run, the working copies were archived here on request, because
the container that held them is temporary and later experiments need the intermediate code
states. Nothing in the analysis reads these files.

| File | Content |
|---|---|
| `<group>-r<rep>.bundle` | git bundle of one series' working copy: the start commit (`site-v0`) plus one commit per accepted backlog item (`impl Bxx`) or maintenance run (`maint_tests`, `maint_refactor`, ...) |
| `manifest.json` | for each series: every commit with its week, the item or maintenance task it adds, and the number of accepted items so far; the last commit of each week |
| `logs.tar.xz` | `transcripts/*.jsonl` (stream-json output of every session), `transcripts/index.csv` (file, session id, run), `ledger.jsonl` (spend ledger) |

`transcripts/index.csv` marks each file as `valid` (179 sessions: 6 calibration, 173 in the six
series; session ids match `docs/data/real/real/tasks.csv`), `invalid_maint_r2_first_run` (22 of
the 29 sessions of the discarded first attempt of maint-r2, see
`docs/data/real/invalid/maint-r2-first-run/README.md`; the other 7 were overwritten by re-run
files with the same name) or `feasibility` (one probe).

The bundles hold tracked files only. `node_modules/`, `dist/` and the acceptance tests are not
in them; run `npm ci` in a restored copy, and copy `acceptance/` from this repository if needed.

## Restore

```sh
python3 -m harness snapshot restore nomaint-r1 --dest /tmp/nomaint-r1            # final state
python3 -m harness snapshot restore nomaint-r1 --items 20 --dest /tmp/n1-k20     # after 20 accepted items
python3 -m harness snapshot restore maint-r3 --week 4 --dest /tmp/m3-w4          # end of week 4
```

`--items K` checks out the last commit with K accepted items, so it includes any maintenance
that ran right after item K. Plain git works too:

```sh
git clone snapshots/maint-r2.bundle /tmp/maint-r2
```

`python3 -m harness snapshot archive` rebuilds this directory from the working copies under
`work_root` in `config/real.toml`.
