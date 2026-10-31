# When the day-15 test runs

Return to this checklist with the exact commit, date, command and smoke-test output. The day-15 test does not call an LLM; it checks the BigQuery fixture, partition metadata, row counts, pruning and HMAC receipt. A pass validates this integration path only, not the model-integrity hypothesis.

## Update the case study

Append a dated section to `CASE_STUDY.md` titled **“Update: what happened when I ran it.”** Include the commit hash, whether the real BigQuery integration ran, the exact pass/fail result, and any useful failure trace. Distinguish code defects from permissions, billing, location or setup failures. Do not rewrite the original narrative as if the result had been known earlier.

## Update the README

Edit **“Status, stated plainly”** in `README.md`. Replace “has not been run” only after the real command executes. Add the date and result. If the test stopped before reaching BigQuery because setup was incomplete, say that the integration remains untested.

## LinkedIn follow-up: choose one outcome

- **Pass:** “The first real BigQuery integration test passed. That validates the fixture and receipt path—not the integrity hypothesis. Next comes the preregistered qualification and holdouts.”
- **Fail:** “The first BigQuery run failed at [specific step]. I’m publishing the error and fixing that issue rather than calling an unexecuted prototype a result.”
- **Skip:** “I didn’t run the BigQuery test this weekend. The repo remains an untested prototype; I’m leaving the status unchanged rather than implying progress that didn’t happen.”

If a bug is being fixed, use: “The day-15 run exposed a bug in [component]. I’ve saved the failing trace and am fixing that specific issue; there is no passing integration result yet.”

Before scored trials, check that task generation, rubric, model ID, thresholds and stopping rules match the timestamped preregistration. Never silently amend the design after seeing results. Record any necessary change with a date and use fresh affected trials.
