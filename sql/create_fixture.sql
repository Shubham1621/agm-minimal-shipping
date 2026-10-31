-- sql/create_fixture.sql
-- Template values are substituted by scripts/day15_smoke.py:
-- {{PROJECT_ID}}, {{DATASET_ID}}
-- Synthetic only. Source data has 100 rows and spans 10 dates to exercise pruning.

CREATE SCHEMA IF NOT EXISTS `{{PROJECT_ID}}.{{DATASET_ID}}`;

CREATE OR REPLACE TABLE `{{PROJECT_ID}}.{{DATASET_ID}}.pipeline_source` (
  event_id INT64 NOT NULL,
  event_date TIMESTAMP NOT NULL,
  customer_id STRING NOT NULL,
  amount NUMERIC NOT NULL,
  payload STRING NOT NULL
);

INSERT INTO `{{PROJECT_ID}}.{{DATASET_ID}}.pipeline_source`
  (event_id, event_date, customer_id, amount, payload)
SELECT
  i AS event_id,
  TIMESTAMP(DATE_ADD(DATE '2025-01-01', INTERVAL MOD(i - 1, 10) DAY)) AS event_date,
  FORMAT('cust-%03d', MOD(i, 20)) AS customer_id,
  CAST(MOD(i * 17, 5000) AS NUMERIC) / 100 AS amount,
  REPEAT(TO_HEX(SHA256(CONCAT(CAST(i AS STRING), '-agm-fixture'))), 32) AS payload
FROM UNNEST(GENERATE_ARRAY(1, 100)) AS i;

-- Shifted schema family: same required partition field, different business key
-- and extra context columns. This is synthetic schema-shift, not production data.
CREATE OR REPLACE TABLE `{{PROJECT_ID}}.{{DATASET_ID}}.pipeline_source_shifted` (
  payment_id INT64 NOT NULL,
  event_date TIMESTAMP NOT NULL,
  customer_id STRING NOT NULL,
  amount NUMERIC NOT NULL,
  payload STRING NOT NULL,
  payment_channel STRING NOT NULL,
  tenant_region STRING NOT NULL
);

INSERT INTO `{{PROJECT_ID}}.{{DATASET_ID}}.pipeline_source_shifted`
  (payment_id, event_date, customer_id, amount, payload, payment_channel, tenant_region)
SELECT
  i AS payment_id,
  TIMESTAMP(DATE_ADD(DATE '2025-01-01', INTERVAL MOD(i - 1, 10) DAY)) AS event_date,
  FORMAT('cust-%03d', MOD(i, 20)) AS customer_id,
  CAST(MOD(i * 23, 7000) AS NUMERIC) / 100 AS amount,
  REPEAT(TO_HEX(SHA256(CONCAT(CAST(i AS STRING), '-agm-shifted'))), 32) AS payload,
  IF(MOD(i, 2) = 0, 'card', 'bank_transfer') AS payment_channel,
  IF(MOD(i, 3) = 0, 'eu-west', 'us-central') AS tenant_region
FROM UNNEST(GENERATE_ARRAY(1, 100)) AS i;

-- Expected target DDL for the canonical matched task. The executable smoke
-- task creates/replaces this table using CREATE TABLE AS SELECT below.
CREATE OR REPLACE TABLE `{{PROJECT_ID}}.{{DATASET_ID}}.pipeline_target` (
  event_id INT64,
  event_date TIMESTAMP,
  customer_id STRING,
  amount NUMERIC,
  payload STRING
)
PARTITION BY DATE(event_date);
