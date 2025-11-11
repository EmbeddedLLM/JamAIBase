#!/bin/bash

# Table to record llm, embed, rerank usage and costs
clickhouse-client --query="CREATE TABLE IF NOT EXISTS jamaibase_owl.llm_usage
(
    \`id\` UUID,
    \`org_id\` String,
    \`proj_id\` String,
    \`user_id\` String,
    \`timestamp\` DateTime64(6, 'UTC'),
    \`model\` String,
    \`input_token\` UInt32,
    \`output_token\` UInt32,
    \`cost\` Decimal128(12),
    \`input_cost\` Decimal128(12),
    \`output_cost\` Decimal128(12)
)
ENGINE=MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (org_id, timestamp, model)"

clickhouse-client --query="CREATE TABLE IF NOT EXISTS jamaibase_owl.embed_usage
(
    \`id\` UUID,
    \`org_id\` String,
    \`proj_id\` String,
    \`user_id\` String,
    \`timestamp\` DateTime64(6, 'UTC'),
    \`model\` String,
    \`num_token\` UInt32,
    \`cost\` Decimal128(12)
)
ENGINE=MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (org_id, timestamp, model)"

clickhouse-client --query="CREATE TABLE IF NOT EXISTS jamaibase_owl.rerank_usage
(
    \`id\` UUID,
    \`org_id\` String,
    \`proj_id\` String,
    \`user_id\` String,
    \`timestamp\` DateTime64(6, 'UTC'),
    \`model\` String,
    \`num_search\` UInt32,
    \`cost\` Decimal128(12)
)
ENGINE=MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (org_id, timestamp, model)"

# Table to record egress usage
clickhouse-client --query="CREATE TABLE IF NOT EXISTS jamaibase_owl.egress_usage
(
    \`id\` UUID,
    \`org_id\` String,
    \`proj_id\` String,
    \`user_id\` String,
    \`timestamp\` DateTime64(6, 'UTC'),
    \`amount_gib\` Decimal128(12),
    \`cost\` Decimal128(12)
)
ENGINE=MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (org_id, timestamp)"

# Table to record file storage usage
clickhouse-client --query="CREATE TABLE IF NOT EXISTS jamaibase_owl.file_storage_usage
(
    \`id\` UUID,
    \`org_id\` String,
    \`proj_id\` String,
    \`user_id\` String,
    \`timestamp\` DateTime64(6, 'UTC'),
    \`amount_gib\` Decimal128(12),
    \`cost\` Decimal128(12),
    \`snapshot_gib\` Decimal128(12)
)
ENGINE=MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (org_id, timestamp)"

# Table to record db storage usage
clickhouse-client --query="CREATE TABLE IF NOT EXISTS jamaibase_owl.db_storage_usage
(
    \`id\` UUID,
    \`org_id\` String,
    \`proj_id\` String,
    \`user_id\` String,
    \`timestamp\` DateTime64(6, 'UTC'),
    \`amount_gib\` Decimal128(12),
    \`cost\` Decimal128(12),
    \`snapshot_gib\` Decimal128(12)
)
ENGINE=MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (org_id, timestamp)"

clickhouse-client --query="CREATE TABLE IF NOT EXISTS jamaibase_owl.owl_traces
(
    \`Timestamp\` DateTime64(9) CODEC(Delta(8), ZSTD(1)),
    \`TraceId\` String CODEC(ZSTD(1)),
    \`SpanId\` String CODEC(ZSTD(1)),
    \`ParentSpanId\` String CODEC(ZSTD(1)),
    \`TraceState\` String CODEC(ZSTD(1)),
    \`SpanName\` LowCardinality(String) CODEC(ZSTD(1)),
    \`SpanKind\` LowCardinality(String) CODEC(ZSTD(1)),
    \`ServiceName\` LowCardinality(String) CODEC(ZSTD(1)),
    \`ResourceAttributes\` Map(LowCardinality(String), String) CODEC(ZSTD(1)),
    \`ScopeName\` String CODEC(ZSTD(1)),
    \`ScopeVersion\` String CODEC(ZSTD(1)),
    \`SpanAttributes\` Map(LowCardinality(String), String) CODEC(ZSTD(1)),
    \`Duration\` Int64 CODEC(ZSTD(1)),
    \`StatusCode\` LowCardinality(String) CODEC(ZSTD(1)),
    \`StatusMessage\` String CODEC(ZSTD(1)),
    \`Events.Timestamp\` Array(DateTime64(9)) CODEC(ZSTD(1)),
    \`Events.Name\` Array(LowCardinality(String)) CODEC(ZSTD(1)),
    \`Events.Attributes\` Array(Map(LowCardinality(String), String)) CODEC(ZSTD(1)),
    \`Links.TraceId\` Array(String) CODEC(ZSTD(1)),
    \`Links.SpanId\` Array(String) CODEC(ZSTD(1)),
    \`Links.TraceState\` Array(String) CODEC(ZSTD(1)),
    \`Links.Attributes\` Array(Map(LowCardinality(String), String)) CODEC(ZSTD(1)),
    INDEX idx_trace_id TraceId TYPE bloom_filter(0.001) GRANULARITY 1,
    INDEX idx_res_attr_key mapKeys(ResourceAttributes) TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX idx_res_attr_value mapValues(ResourceAttributes) TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX idx_span_attr_key mapKeys(SpanAttributes) TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX idx_span_attr_value mapValues(SpanAttributes) TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX idx_duration Duration TYPE minmax GRANULARITY 1
)
ENGINE = MergeTree
PARTITION BY toDate(Timestamp)
ORDER BY (ServiceName, SpanName, toUnixTimestamp(Timestamp), TraceId)
TTL toDateTime(Timestamp) + toIntervalDay(3)
SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1"


clickhouse-client --query="CREATE TABLE IF NOT EXISTS jamaibase_owl.owl_traces_trace_id_ts
(
	\`TraceId\` String CODEC(ZSTD(1)),
	\`Start\` DateTime64(9) CODEC(Delta(8), ZSTD(1)),
	\`End\` DateTime64(9) CODEC(Delta(8), ZSTD(1)),
	INDEX idx_trace_id TraceId TYPE bloom_filter(0.01) GRANULARITY 1
)
ENGINE = MergeTree
ORDER BY (TraceId, toUnixTimestamp(Start))
TTL toDateTime(Start) + toIntervalDay(3)"


clickhouse-client --query="CREATE MATERIALIZED VIEW IF NOT EXISTS jamaibase_owl.owl_traces_trace_id_ts_mv TO jamaibase_owl.owl_traces_trace_id_ts
(
	\`TraceId\` String,
	\`Start\` DateTime64(9),
	\`End\` DateTime64(9)
) AS
SELECT
	TraceId,
	min(Timestamp) AS Start,
	max(Timestamp) AS End
FROM jamaibase_owl.owl_traces
WHERE TraceId != ''
GROUP BY TraceId"

# Table using Json data type
# clickhouse-client --query="CREATE TABLE IF NOT EXISTS jamaibase_owl.owl_usage 
# (
#     \`id\` UUID,
#     \`org_id\` String,
#     \`timestamp\` DateTime64(6, 'UTC'),
#     \`data\` JSON()
# )
# ENGINE=MergeTree ORDER BY (org_id, timestamp)"

### --- Migrations --- ###

clickhouse-client --query="ALTER TABLE jamaibase_owl.egress_usage RENAME COLUMN IF EXISTS amount_gb to amount_gib"
clickhouse-client --query="ALTER TABLE jamaibase_owl.llm_usage MODIFY COLUMN cost Decimal128(12)"
clickhouse-client --query="ALTER TABLE jamaibase_owl.llm_usage MODIFY COLUMN input_cost Decimal128(12)"
clickhouse-client --query="ALTER TABLE jamaibase_owl.llm_usage MODIFY COLUMN output_cost Decimal128(12)"
clickhouse-client --query="ALTER TABLE jamaibase_owl.embed_usage MODIFY COLUMN cost Decimal128(12)"
clickhouse-client --query="ALTER TABLE jamaibase_owl.rerank_usage MODIFY COLUMN cost Decimal128(12)"
clickhouse-client --query="ALTER TABLE jamaibase_owl.egress_usage MODIFY COLUMN cost Decimal128(12)"
clickhouse-client --query="ALTER TABLE jamaibase_owl.egress_usage MODIFY COLUMN amount_gib Decimal128(12)"