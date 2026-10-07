# Invalid run: maint group, rep 2 (first attempt)

Kept for audit only. Not used in the dashboard or the report.

In week 3 a maintenance session (maint_tests) started a background task, so the CLI emitted two
`result` events. The harness read token usage only from the last one, which covers only the
final turn, and logged 0.0081 USD instead of the session's real 0.1719 USD (sum of both turns;
it matches the CLI's cumulative modelUsage). The scheduling loop therefore saw 0.16 USD more
remaining budget in week 3 than it had, and started items B10 and B11 that the rules would not
have allowed. Every later week of this series depends on that.

The parser was fixed (usage is now summed over all result events and checked against the
cumulative modelUsage), all 182 transcripts were re-checked against the CLI's cumulative cost,
and this series was re-run from the start with otherwise identical settings. No other session
had more than one result event.
