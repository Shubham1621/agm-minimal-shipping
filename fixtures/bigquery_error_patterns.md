<!-- fixtures/bigquery_error_patterns.md -->
# BigQuery error and verifier classification notes

For invalid GoogleSQL, the Python client ordinarily raises
`google.api_core.exceptions.BadRequest` (HTTP 400). Do not rely on the entire
human-readable message being byte-for-byte stable.

- **Omitted from SELECT:** the query retains `PARTITION BY DATE(event_date)` but
  the SELECT output drops `event_date`. Expected message pattern:
  `Unrecognized name: event_date` or semantically equivalent unresolved-name
  text. The verifier also checks the known SQL shape and emits
  `PARTITION_COLUMN_OMITTED`.
- **Misspelled partition field:** SQL uses `PARTITION BY DATE(event_dtae)` while
  selecting the valid `event_date`. Expected message pattern:
  `Unrecognized name: event_dtae`; verifier emits `PARTITION_COLUMN_MISSPELLED`.
- **Missing partition expression:** query can succeed while creating an
  unpartitioned table. There is no expected BigQuery error. The verifier
  inspects `Table.time_partitioning` and emits `PARTITION_EXPRESSION_MISSING`.

These patterns are benchmark-specific expectations, not a stable API promise.
The signed receipt preserves the raw server message.
