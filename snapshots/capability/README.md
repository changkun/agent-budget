# Capability experiment: code states and logs

Code states of the follow-up experiment ([PLAN-capability.md](../../PLAN-capability.md),
[REPORT-capability.md](../../REPORT-capability.md)). Nothing in the analysis reads these files;
the analysis reads `docs/data/capability/`.

| File | Content |
|---|---|
| `v0.bundle` | site-v0, tag `v0` |
| `sonnet55-r<rep>.bundle` | Sonnet's no-maintenance series from the first experiment, with tags `sonnet55-r<rep>-k15-R`, `-k29-R` and the maintained states `-k15-M<model>`, `-k29-M<model>` |
| `haiku55-r<rep>.bundle`, `opus55-r<rep>.bundle` | the producer series (one commit per accepted item, B01-B29), tag `<model>-r<rep>-k29-R`, and the maintained states `-k29-Msonnet55`, `-k29-M<model>` |
| `logs.tar.xz` | `transcripts/` (stream-json of every session), `ledger.jsonl` (spend ledger), `jobs.jsonl` (job status log), `run.log` |

A state is a tag. To restore one:

```sh
git init /tmp/state && cd /tmp/state
git fetch /path/to/snapshots/capability/opus55-r2.bundle refs/tags/opus55-r2-k29-Msonnet55:refs/tags/opus55-r2-k29-Msonnet55
git checkout -b work opus55-r2-k29-Msonnet55
npm ci
```

`python3 -m harness capability archive` rebuilds this directory from the working store under
`work_root` in `config/capability.toml`.
