I spent fourteen design cycles on a research idea. Then I realized I couldn't ship the experiment solo in 90 days. So I published the design instead of waiting for the result.

The idea is an integrity gate for AI data-pipeline agents: can a 60-trial sandbox qualification predict whether an agent accurately reports failures in new contexts?

Three concrete things came out of the design:

First, a BigQuery partition-column failure is the test case. A query can fail loudly—or create an unpartitioned table that appears to have succeeded.

Second, the design separates task capability from reporting integrity. A successful-looking output should not compensate for a false report about a failed verifier.

Third, the proposed probe compares structured status fields with free-text commentary, then checks whether a blinded reviewer catches a misleading handoff. Qualification, matched holdout, and shifted holdout are separate so the result can fail honestly.

The important qualification: this is a research design and a code prototype, not an experiment result. The code has never run against BigQuery. The next step is a weekend project: run the day-15 integration test against a personal GCP project, then decide whether the harness is ready for scored trials.

If you have BigQuery + Anthropic API access and want to co-run the qualification set, or if you've built something adjacent, I'd like to hear from you. Specific criticism of the measurement is just as useful as help running it.

Repository: [REPO LINK]

#AIEngineering #DataEngineering
