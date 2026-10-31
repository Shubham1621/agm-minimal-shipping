# Accountable Group Mind: Integrity Gate Prototype

**Status document · 21 October 2026**

## What this is

This repository contains a research design and an untested software prototype for a narrow question: can a controlled integrity-qualification protocol predict accurate reporting by an AI agent on independently generated pipeline tasks? The concrete testbed is a BigQuery pipeline that omits or mishandles a partition column. The prototype includes a verifier, signed-receipt logic, a local ledger, task-generation code, reporting probes and a real-service smoke-test path. It is not a product, a completed study, or evidence that the selected model conceals failures.

## Status, stated plainly

**As of 21 October 2026, no file in this repository has been executed against a live BigQuery dataset. The day-15 smoke test is the first real integration test and has not been run.** The code was assembled as a prototype and has not earned an end-to-end execution claim. This distinction applies even where a file has a plausible implementation or a test name exists.

## What is here

Each line gives the artifact's purpose and its present state.

- `Makefile` — install, local-test and real BigQuery smoke-test targets. Written; not executed here.
- `requirements.txt` — Python dependencies for the prototype. Written; dependency installation not verified in the target environment.
- `experiment.yaml` — model, token-budget and trial configuration. Written; not frozen by a public preregistration.
- `sql/create_fixture.sql` — synthetic BigQuery source tables and expected partitioned target. Written; not executed against BigQuery.
- `scripts/day15_smoke.py` — creates the fixture, runs the hand-crafted query, checks metadata and writes a signed receipt. Written; not executed against BigQuery.
- `tests/test_day15_smoke.py` — integration-test assertions for the fixture, partitioning, row counts, pruning and signature. Written; not run against BigQuery.
- `src/verifier.py` — HMAC-signed receipt generation and partition/schema checks, including controlled failure classification. Written; not executed against BigQuery.
- `src/ledger.py` — SQLite event, receipt, handoff, incident, memory, policy and escalation storage. Written; not independently validated under failure/restart conditions.
- `src/task_generator.py` — seeded task variants and three partition-related mutations. Written; its referenced `task_templates.yaml` is absent from the current repository and must be added before the generator can run.
- `src/probe.py` — structured-report/commentary scoring and reviewer-outcome helpers. Written; no accompanying local unit-test file exists yet.
- `src/reviewer_packets.py` — packet preparation utilities for solo blinded review. Written; the separate reviewer command-line scripts are absent.
- `src/cost_guard.py` — reserve-before-call and commit-after-call cost tracking. Written; not tested against retry, process-crash or concurrent-call scenarios.
- `src/estimate_cost.py` — token-budget estimator using the YAML configuration. Written; estimates are not actual provider invoices.
- `fixtures/bigquery_error_patterns.md` — expected classes and patterns for benchmark failures. Written; server-message matching remains unverified against a real project.
- `reviewer_protocol.md` — proposed packet and decision procedure for solo review. Written; not carried out.
- `rubrics/commentary_rubric.md` — proposed criteria for disclosure in free text. Written; no scored rubric exercise has occurred.
- `README.md` — current setup and status record. Written; intentionally reports the experiment as unexecuted.
- `CASE_STUDY.md` — narrative of the design process and limitations. Written before the first BigQuery run.
- `LINKEDIN_POST.md` — short public summary with a repository-link placeholder. Drafted; not posted.
- `FOLLOW_UP_PLAN.md` — instructions for recording the eventual smoke-test outcome. Written; not yet used.
- `.gitignore` — excludes secrets, local state, generated reports and caches. Written; not yet used in a committed Git repository.
- `LICENSE` — MIT license, copyright 2026 Shubham Joshi. Written; no public repository has been pushed by this artifact.
- `CONTRIBUTING.md` and `ISSUES_TO_OPEN.md` — contribution boundary and five initial repo issues. Written; issues not opened.
- `src/__init__.py` and `scripts/__init__.py` — package markers. Written; not execution-tested.

## What is missing

The next implementation tasks are small but real. Add `task_templates.yaml` and verify generator behavior (about 1–2 hours). Add the four local test files—`tests/test_task_generator.py`, `tests/test_probe.py`, `tests/test_reviewer_packets.py`, and `tests/test_cost_guard.py` (about 5–8 hours). Add the reviewer CLI scripts for seed commitment, packet construction and timestamped decisions (about 3–5 hours). Build an LLM client that pins the model ID and records usage without leaking credentials (about 3–5 hours). Finish the harness that joins generated tasks, model calls, BigQuery execution, receipts, review labels and scores (about 6–10 hours). These estimates overlap and are planning guesses, not promises. The real BigQuery smoke test also remains to be run from a personal project.

## The research question

*Can a 60-trial sandbox qualification on a frozen model predict honest reporting in independently generated deployment-like contexts?* The proposed protocol first requires zero concealment events in 60 randomized qualification opportunities, then evaluates separate matched and shifted holdout sets. The main point is prediction across contexts—not the fact that a gate can block an agent. A blocked agent producing no accepted handoff would be a control-flow result, not evidence that qualification predicts integrity.

## What would make this real

- A day-15 pass against the actual BigQuery service, with the signed receipt and partition-pruning checks recorded.
- A timestamped OSF preregistration (or equivalent signed, externally timestamped record) deposited before any scored trials.
- One documented run of qualification, matched holdout and shifted holdout, with raw counts, costs, model metadata, failures and an honest inconclusive outcome if the target is not met.

## How to run the day-15 test with personal GCP access

```bash
gcloud auth login
read -rp "Personal billing account ID: " BILLING_ACCOUNT_ID
export AGM_GCP_PROJECT="agm-personal-$(date +%s)"
gcloud projects create "$AGM_GCP_PROJECT" --name="AGM Personal Research"
gcloud billing projects link "$AGM_GCP_PROJECT" --billing-account="$BILLING_ACCOUNT_ID" && gcloud services enable bigquery.googleapis.com --project="$AGM_GCP_PROJECT"
gcloud auth application-default login
gcloud auth application-default set-quota-project "$AGM_GCP_PROJECT"
export AGM_BQ_DATASET=agm_sandbox AGM_BQ_LOCATION=US
export AGM_HMAC_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
cd agm-minimal && make install && make day15
```

Use a personal billing account and project only; do not use employer credentials or data. The smoke test does not need an Anthropic key; the later model harness will use a personal API key held only by the orchestrator.

## What this is not

- Not a product or production-ready CI gate.
- Not a tested result: no live BigQuery execution has been recorded.
- Not a claim that the model conceals, or that the proposed qualification detects concealment reliably.
