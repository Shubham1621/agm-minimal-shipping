# Issues to open after publishing the repository

Open these five issues in order. Suggested labels are included; create the labels if the repository does not have them yet.

## 1. Weekend project: run the day-15 BigQuery smoke test

**Body:** Provision a personal GCP project, enable BigQuery, configure ADC and the required environment variables, then run `make day15` against the real BigQuery service. Attach the command, sanitized traceback or PASS output, and `reports/day15_smoke.json` with project identifiers reviewed before publication. Do not attach credentials or secret values. This issue closes only on a real BigQuery run; mocked results do not count.

**Label:** `integration-test`

## 2. Add the four missing local test files

**Body:** Add the missing `task_templates.yaml` required by `src/task_generator.py`, then add `tests/test_task_generator.py`, `tests/test_probe.py`, `tests/test_reviewer_packets.py`, and `tests/test_cost_guard.py`. Tests should cover deterministic seeded generation, all three mutation codes, two-surface disclosure scoring, reviewer packet redaction/shuffling, and reserve-before-call/cap enforcement. Confirm the local `make test` target returns success rather than an empty test-suite status. Do not label these tests as passed until they have actually run.

**Label:** `tests`

## 3. Deposit the preregistration before scored runs

**Body:** Review the protocol against the current code and task allocation, resolve any discrepancy before scoring, then deposit a timestamped preregistration on OSF or create a signed Git tag with an externally timestamped archive. Record the exact commit, model ID, thresholds, generator seed policy, commentary rubric, reviewer protocol and stopping rules. The current public case study must state clearly that no scored run has occurred yet.

**Label:** `research-integrity`

## 4. Does the two-surface probe measure honesty or field-sensitivity?

**Body:** Assess whether structured JSON status and free-text commentary should be treated as two indicators of one reporting construct or as different behaviors. Specify how disagreement is scored, how commentary is double-rated by one researcher, and what evidence would justify any claim beyond this task and model. Do not infer intent from a discrepancy alone.

**Label:** `research-question`

## 5. Is integrity a model, harness, or institutional property?

**Body:** Critique the boundary between model behavior, tool/harness permissions, independent evidence, role eligibility, and organizational policy. In particular, identify which claims can be tested with a frozen model and which require repeated model versions, independent raters or longer-horizon institution-level experiments.

**Label:** `research-question`
