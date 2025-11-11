from __future__ import annotations

import re
from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger

from owl.types import ProductType, Usage, UsageResponse
from owl.utils.billing import ClickHouseAsyncClient
from owl.utils.exceptions import BadInputError


###############################################################################
# 1.  Column-level registry
###############################################################################
@dataclass(frozen=True, slots=True)
class _BaseTable:
    org_col: str = "org_id"
    proj_col: str = "proj_id"
    user_col: str = "user_id"
    model_col: str = "model"
    ts_col: str = "timestamp"
    ts_interval: str = "timestamp_interval"

    def valid_group_by_cols(self) -> list[str]:
        return [
            self.org_col,
            self.proj_col,
            self.user_col,
            self.model_col,
        ]


@dataclass(frozen=True, slots=True)
class LlmTable(_BaseTable):
    table_id: str = "llm_usage"
    input_col: str = "input_token"
    output_col: str = "output_token"
    input_cost_col: str = "input_cost"
    output_cost_col: str = "output_cost"
    result_input_token: str = "input"
    result_output_token: str = "output"
    result_total_token: str = "total_token"
    category_total: str = "total_cost"

    def valid_group_by_cols(self) -> list[str]:
        return _BaseTable().valid_group_by_cols() + ["type"]


@dataclass(frozen=True, slots=True)
class EmbedTable(_BaseTable):
    table_id: str = "embed_usage"
    value_col: str = "num_token"
    cost_col: str = "cost"


@dataclass(frozen=True, slots=True)
class RerankTable(_BaseTable):
    table_id: str = "rerank_usage"
    value_col: str = "num_search"
    cost_col: str = "cost"


@dataclass(frozen=True, slots=True)
class EgressTable(_BaseTable):
    table_id: str = "egress_usage"
    value_col: str = "amount_gib"
    cost_col: str = "cost"
    model_col: str = "bandwidth"  # Egress actually does not have model
    type: str = "egress"  # to align with vm

    def valid_group_by_cols(self) -> list[str]:
        _valid = _BaseTable().valid_group_by_cols() + ["type"]
        _valid.remove(_BaseTable().model_col)
        return _valid


@dataclass(frozen=True, slots=True)
class FileStorageTable(_BaseTable):
    table_id: str = "file_storage_usage"
    value_col: str = "amount_gib"
    cost_col: str = "cost"
    snapshot_col: str = "snapshot_gib"
    model_col: str = "file_storage"  # FileStorage actually does not have model
    type: str = "file"  # used for grouping

    def valid_group_by_cols(self) -> list[str]:
        _valid = _BaseTable().valid_group_by_cols() + ["type"]
        _valid.remove(_BaseTable().model_col)
        return _valid


# For Storage usage type, = file/db
@dataclass(frozen=True, slots=True)
class DBStorageTable(_BaseTable):
    table_id: str = "db_storage_usage"
    value_col: str = "amount_gib"
    cost_col: str = "cost"
    snapshot_col: str = "snapshot_gib"
    model_col: str = "db_storage"  # DBStorage actually does not have model
    type: str = "db"  # used for grouping

    def valid_group_by_cols(self) -> list[str]:
        _valid = _BaseTable().valid_group_by_cols() + ["type"]
        _valid.remove(_BaseTable().model_col)
        return _valid


# HACK: This is not an actual clickhouse table just to make it work with other parts
# For Storage spent, category = file/db (no type)
@dataclass(frozen=True, slots=True)
class CostTable(_BaseTable):
    llm_table: LlmTable = LlmTable()
    embed_table: EmbedTable = EmbedTable()
    rerank_table: RerankTable = RerankTable()
    egress_table: EgressTable = EgressTable()
    file_storage_table: FileStorageTable = FileStorageTable()
    db_storage_table: DBStorageTable = DBStorageTable()
    category_total: str = "cost"
    category_llm_input: str = "input_cost"
    category_llm_output: str = "output_cost"
    llm_input_type: str = "input"
    llm_output_type: str = "output"
    category_llm: str = ProductType.LLM_TOKENS.value
    category_embed: str = ProductType.EMBEDDING_TOKENS.value
    category_rerank: str = ProductType.RERANKER_SEARCHES.value
    category_egress: str = ProductType.EGRESS.value
    category_file_storage: str = ProductType.FILE_STORAGE.value
    category_db_storage: str = ProductType.DB_STORAGE.value

    # HACK: so the table_id get from with_where_clause
    table_id: str = ""

    # HACK: to make this compatible with victoriametrics query
    def valid_group_by_cols(self) -> list[str]:
        return _BaseTable().valid_group_by_cols() + ["type", "category"]

    def build_table_id(self, where_clause: str = "") -> str:
        """Return the table_id with WHERE clause injected into each subquery"""
        base_where = f"WHERE {where_clause}" if where_clause else ""
        # HACK: the egress table does not have model_col, put model as 'bandwidth'
        # HACK: the file_storage and db_storage table does not have model_col, put model as 'file_storage' and 'db_storage'
        return f"""(
        SELECT {self.llm_table.org_col}, {self.llm_table.proj_col}, {self.llm_table.model_col}, {self.llm_table.ts_col},  {self.llm_table.input_cost_col},  {self.llm_table.output_cost_col},  {self.llm_table.input_cost_col} + {self.llm_table.output_cost_col} as {self.category_llm}, 0 as {self.category_embed}, 0 as {self.category_rerank}, 0 as {self.category_egress}, 0 as {self.category_file_storage}, 0 as {self.category_db_storage}
            FROM {self.llm_table.table_id}
            {base_where}
        UNION ALL
        SELECT {self.embed_table.org_col}, {self.embed_table.proj_col}, {self.embed_table.model_col}, {self.embed_table.ts_col}, 0 as {self.llm_table.input_cost_col},  0 as {self.llm_table.output_cost_col}, 0 as {self.category_llm}, {self.embed_table.cost_col} as {self.category_embed}, 0 as {self.category_rerank}, 0 as {self.category_egress}, 0 as {self.category_file_storage}, 0 as {self.category_db_storage}
            FROM {self.embed_table.table_id}
            {base_where}
        UNION ALL
        SELECT {self.rerank_table.org_col}, {self.rerank_table.proj_col}, {self.rerank_table.model_col}, {self.rerank_table.ts_col}, 0 as {self.llm_table.input_cost_col},  0 as {self.llm_table.output_cost_col}, 0 as {self.category_llm}, 0 as {self.category_embed}, {self.rerank_table.cost_col} as {self.category_rerank}, 0 as {self.category_egress}, 0 as {self.category_file_storage}, 0 as {self.category_db_storage}
            FROM {self.rerank_table.table_id}
            {base_where}
        UNION ALL
        SELECT {self.egress_table.org_col}, {self.egress_table.proj_col}, '{self.egress_table.model_col}' as {_BaseTable().model_col}, {self.egress_table.ts_col}, 0 as {self.llm_table.input_cost_col},  0 as {self.llm_table.output_cost_col}, 0 as {self.category_llm}, 0 as {self.category_embed}, {self.rerank_table.cost_col} as {self.category_rerank}, {self.egress_table.cost_col} as {self.category_egress}, 0 as {self.category_file_storage}, 0 as {self.category_db_storage}
            FROM {self.egress_table.table_id}
            {base_where}
        UNION ALL
        SELECT {self.file_storage_table.org_col}, {self.file_storage_table.proj_col}, '{self.file_storage_table.model_col}' as {_BaseTable().model_col}, {self.file_storage_table.ts_col}, 0 as {self.llm_table.input_cost_col},  0 as {self.llm_table.output_cost_col}, 0 as {self.category_llm}, 0 as {self.category_embed}, {self.rerank_table.cost_col} as {self.category_rerank}, 0 as {self.category_egress}, {self.file_storage_table.cost_col} as {self.category_file_storage}, 0 as {self.category_db_storage}
            FROM {self.file_storage_table.table_id}
            {base_where}
        UNION ALL
        SELECT {self.db_storage_table.org_col}, {self.db_storage_table.proj_col}, '{self.db_storage_table.model_col}' as {_BaseTable().model_col}, {self.db_storage_table.ts_col}, 0 as {self.llm_table.input_cost_col},  0 as {self.llm_table.output_cost_col}, 0 as {self.category_llm}, 0 as {self.category_embed}, {self.rerank_table.cost_col} as {self.category_rerank}, 0 as {self.category_egress}, 0 as {self.category_file_storage}, {self.db_storage_table.cost_col} as {self.category_db_storage}
            FROM {self.db_storage_table.table_id}
            {base_where}
        )"""

    def row_is_llm(self, row: dict[str, Any]) -> bool:
        # special handling to remove non llm type (when group by with 'model')
        if row.get(self.model_col, "") in [
            self.egress_table.model_col,
            self.file_storage_table.model_col,
            self.db_storage_table.model_col,
        ]:
            return False
        return True


###############################################################################
# 2.  Helper utilities
###############################################################################
_duration_units = {
    "ms": timedelta(milliseconds=1),
    "s": timedelta(seconds=1),
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
    "y": timedelta(days=365),
}

_interval_map = {
    "s": "SECOND",
    "m": "MINUTE",
    "h": "HOUR",
    "d": "DAY",
    "w": "WEEK",
    "y": "YEAR",
}

MetricDef = namedtuple("MetricDef", ["name", "value_col", "extra_dims", "gb_mask"])

_METRICS: tuple[MetricDef, ...] = (
    MetricDef(
        "embed", CostTable().category_embed, {"category": CostTable().category_embed}, "embed"
    ),
    MetricDef(
        "rerank", CostTable().category_rerank, {"category": CostTable().category_rerank}, "rerank"
    ),
    MetricDef(
        "egress", CostTable().category_egress, {"category": CostTable().category_egress}, "egress"
    ),
    MetricDef(
        "file",
        CostTable().category_file_storage,
        {"category": CostTable().category_file_storage},
        "file",
    ),
    MetricDef(
        "db", CostTable().category_db_storage, {"category": CostTable().category_db_storage}, "db"
    ),
    MetricDef(
        "llm_input",
        CostTable().category_llm_input,
        {"category": CostTable().category_llm, "type": CostTable().llm_input_type},
        "common",
    ),
    MetricDef(
        "llm_output",
        CostTable().category_llm_output,
        {"category": CostTable().category_llm, "type": CostTable().llm_output_type},
        "common",
    ),
    MetricDef("llm", CostTable().category_llm, {"category": CostTable().category_llm}, "common"),
    MetricDef("total", CostTable().category_total, {}, "common"),
)


def _parse_duration(duration: str) -> timedelta:
    delta = timedelta()
    for value, unit in re.findall(r"(\d+)([smhdwy])", duration):
        delta += int(value) * _duration_units[unit]
    return delta


def _parse_interval(window_size: str) -> str:
    m = re.fullmatch(r"(\d+)([smhdwy])", window_size)
    if not m or m.group(2) not in _interval_map:
        raise BadInputError(f"Bad window_size {window_size!r}, expected s/m/h/d/w/y")

    number = m.group(1)
    unit = _interval_map[m.group(2)]
    return f"{number} {unit}"


def _in_filter(col: str, values: list[str] | None) -> str:
    if not values:
        return "1=1"
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{col} IN ({quoted})"


def _filter_groupby(group_by: list[str], invalids: list[str] | None = None) -> list[str]:
    if invalids is None:
        invalids = []
    return [g for g in group_by if g not in invalids]


def _build_gb_filters(has_category: bool, has_type: bool, has_model: bool) -> dict[str, list[str]]:
    base = [] if has_category else ["category"]
    filters = {mask: base.copy() for mask in ("common", "embed", "rerank", "egress", "file", "db")}
    if has_type:
        for m in ("embed", "rerank", "egress", "file", "db"):
            filters[m].append("type")
    if has_model:
        for m in ("file", "db", "egress"):
            filters[m].append("model")
    return filters


def _get_active_metrics(has_category: bool, has_type: bool) -> list[MetricDef]:
    if not has_category:
        if has_type:
            # not has_category and has_type
            return [m for m in _METRICS if m.name in {"llm_input", "llm_output", "total"}]
        # has_category and has_type
        return [m for m in _METRICS if m.name == "total"]
    if has_type:
        # has_category and has_type
        return [
            m
            for m in _METRICS
            if m.name in {"embed", "rerank", "egress", "llm_input", "llm_output", "file", "db"}
        ]
    # has_category and not has_type
    return [m for m in _METRICS if m.name in {"embed", "rerank", "egress", "file", "db", "llm"}]


###############################################################################
# 3.  Generic query builder
###############################################################################
def _build_time_bucket_query(
    spec: LlmTable
    | EmbedTable
    | RerankTable
    | EgressTable
    | FileStorageTable
    | DBStorageTable
    | CostTable,
    org_ids: list[str] | None,
    proj_ids: list[str] | None,
    from_: datetime,
    to: datetime,
    group_by: list[str],
    window_size: str,
) -> tuple[str, timedelta]:
    for group in group_by:
        if group not in spec.valid_group_by_cols():
            raise BadInputError(
                f"Invalid group_by column: {group}, must be one of {spec.valid_group_by_cols()}"
            )

    org_c = _in_filter(spec.org_col, org_ids)
    proj_c = _in_filter(spec.proj_col, proj_ids)
    interval = _parse_interval(window_size)
    ts_alias = f"toStartOfInterval({spec.ts_col}, INTERVAL {interval}) AS {spec.ts_interval}"

    has_type = "type" in group_by
    has_category = "category" in group_by
    if has_type:
        group_by.remove("type")
    if has_category:
        group_by.remove("category")

    select_cols = [ts_alias, *group_by]

    # where clause
    where_clause = f"""{spec.ts_col} >= '{from_:%Y-%m-%d %H:%M:%S}'
            AND {spec.ts_col} < '{to:%Y-%m-%d %H:%M:%S}'
            AND {org_c}
            AND {proj_c}
        """
    # Value expression
    if isinstance(spec, LlmTable):
        if has_type:
            value_expr = f"SUM({spec.input_col}) as {spec.result_input_token}, SUM({spec.output_col}) as {spec.result_output_token}"
        else:
            value_expr = f"SUM({spec.input_col} + {spec.output_col}) AS {spec.result_total_token}"
    elif isinstance(spec, FileStorageTable) or isinstance(spec, DBStorageTable):
        value_expr = f"MAX({spec.snapshot_col}) AS {spec.snapshot_col}"
    elif isinstance(spec, CostTable):
        if has_category:
            if has_type:
                value_expr = f"SUM({spec.category_llm_input}) AS {spec.category_llm_input}, SUM({spec.category_llm_output}) AS {spec.category_llm_output}, SUM({spec.category_embed}) AS {spec.category_embed}, SUM({spec.category_rerank}) AS {spec.category_rerank}, SUM({spec.category_egress}) AS {spec.category_egress}, SUM({spec.category_file_storage}) AS {spec.category_file_storage}, SUM({spec.category_db_storage}) AS {spec.category_db_storage}"
            else:
                value_expr = f"SUM({spec.category_llm}) AS {spec.category_llm}, SUM({spec.category_embed}) AS {spec.category_embed}, SUM({spec.category_rerank}) AS {spec.category_rerank}, SUM({spec.category_egress}) AS {spec.category_egress}, SUM({spec.category_file_storage}) AS {spec.category_file_storage}, SUM({spec.category_db_storage}) AS {spec.category_db_storage}"
        else:
            if has_type:
                value_expr = f"SUM({spec.category_llm_input}) as {spec.category_llm_input}, SUM({spec.category_llm_output}) as {spec.category_llm_output}, SUM({spec.category_embed} + {spec.category_rerank} + {spec.category_egress} + {spec.category_file_storage} + {spec.category_db_storage}) AS {spec.category_total}"
            else:
                value_expr = f"SUM({spec.category_llm} + {spec.category_embed} + {spec.category_rerank} + {spec.category_egress} + {spec.category_file_storage} + {spec.category_db_storage}) AS {spec.category_total}"
    else:
        value_expr = f"SUM({spec.value_col}) AS {spec.value_col}"
    select_cols.append(value_expr)

    group_clause = ", ".join([spec.ts_interval, *group_by])
    sql = f"""
    SELECT {", ".join(select_cols)}
    FROM {spec.table_id or spec.build_table_id(where_clause)}
    WHERE {where_clause}
    GROUP BY {group_clause}
    ORDER BY {spec.ts_interval}
    """
    return sql, _parse_duration(window_size)


###############################################################################
# 4.  Billing service
###############################################################################
class BillingMetrics:
    def __init__(self, clickhouse_client: ClickHouseAsyncClient) -> None:
        self.client = clickhouse_client

    async def _query(self, sql: str) -> list[dict[str, Any]]:
        try:
            res = await self.client.query(sql)
            logger.info(
                f"Query ID {res.summary.get('query_id')} "
                f"rows={res.summary.get('result_rows')} "
                f"elapsed={res.summary.get('elapsed_ns')}ns"
            )
            if res.summary.get("result_rows") == "0":
                return []
            return [
                dict(zip(res.column_names, row, strict=True))
                for row in zip(*res.result_columns, strict=True)
            ]
        except Exception as e:
            logger.error(f"Query failed: {sql} – {e}")
            raise

    @staticmethod
    def _process_group_by(group_by: list[str]) -> list[str]:
        # if "organization_id" in group_by:
        #     group_by.remove("organization_id")
        # if "project_id" in group_by:
        #     group_by.remove("project_id")
        #     group_by.append("proj_id")
        group_by = list(set([_BaseTable().org_col] + group_by))
        return group_by

    # ------------------------------------------------------------------
    #  Public API – unchanged signatures
    # ------------------------------------------------------------------
    async def query_llm_usage(
        self,
        filtered_by_org_id: list[str] | None,
        filtered_by_proj_id: list[str] | None,
        from_: datetime,
        to: datetime | None,
        group_by: list[str],
        window_size: str,
    ) -> UsageResponse:
        table = LlmTable()
        to = to or datetime.now(timezone.utc)
        group_by = self._process_group_by(group_by)
        # group_by might be modified
        sql, interval = _build_time_bucket_query(
            table, filtered_by_org_id, filtered_by_proj_id, from_, to, group_by.copy(), window_size
        )
        rows = await self._query(sql)
        if "type" in group_by:
            usages = []
            for r in rows:
                usages.append(
                    Usage.from_result(
                        [
                            int((r.get(table.ts_interval) + interval).timestamp()),
                            r.get(table.result_input_token),
                        ],
                        {**r, "type": table.result_input_token},
                        interval,
                        group_by,
                    )
                )
                usages.append(
                    Usage.from_result(
                        [
                            int((r.get(table.ts_interval) + interval).timestamp()),
                            r.get(table.result_output_token),
                        ],
                        {**r, "type": table.result_output_token},
                        interval,
                        group_by,
                    )
                )
        else:
            usages = [
                Usage.from_result(
                    [
                        int((r.get(table.ts_interval) + interval).timestamp()),
                        r.get(table.result_total_token),
                    ],
                    r,
                    interval,
                    group_by,
                )
                for r in rows
            ]
        return UsageResponse(
            windowSize=window_size,
            data=usages,
            start=from_.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end=to.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    async def query_embedding_usage(
        self,
        filtered_by_org_id: list[str] | None,
        filtered_by_proj_id: list[str] | None,
        from_: datetime,
        to: datetime | None,
        group_by: list[str],
        window_size: str,
    ) -> UsageResponse:
        table = EmbedTable()
        to = to or datetime.now(timezone.utc)
        group_by = self._process_group_by(group_by)
        sql, interval = _build_time_bucket_query(
            table, filtered_by_org_id, filtered_by_proj_id, from_, to, group_by.copy(), window_size
        )
        rows = await self._query(sql)
        return UsageResponse(
            windowSize=window_size,
            data=[
                Usage.from_result(
                    [
                        int((r.get(table.ts_interval) + interval).timestamp()),
                        r.get(table.value_col),
                    ],
                    r,
                    interval,
                    group_by,
                )
                for r in rows
            ],
            start=from_.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end=to.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    async def query_reranking_usage(
        self,
        filtered_by_org_id: list[str] | None,
        filtered_by_proj_id: list[str] | None,
        from_: datetime,
        to: datetime | None,
        group_by: list[str],
        window_size: str,
    ) -> UsageResponse:
        table = RerankTable()
        to = to or datetime.now(timezone.utc)
        group_by = self._process_group_by(group_by)
        sql, interval = _build_time_bucket_query(
            table,
            filtered_by_org_id,
            filtered_by_proj_id,
            from_,
            to,
            group_by.copy(),
            window_size,
        )
        rows = await self._query(sql)
        return UsageResponse(
            windowSize=window_size,
            data=[
                Usage.from_result(
                    [
                        int((r.get(table.ts_interval) + interval).timestamp()),
                        r.get(table.value_col),
                    ],
                    r,
                    interval,
                    group_by,
                )
                for r in rows
            ],
            start=from_.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end=to.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    async def query_bandwidth(
        self,
        filtered_by_org_id: list[str] | None,
        filtered_by_proj_id: list[str] | None,
        from_: datetime,
        to: datetime | None,
        group_by: list[str],
        window_size: str,
    ) -> UsageResponse:
        table = EgressTable()
        to = to or datetime.now(timezone.utc)
        group_by = self._process_group_by(group_by)
        has_type = "type" in group_by
        sql, interval = _build_time_bucket_query(
            table,
            filtered_by_org_id,
            filtered_by_proj_id,
            from_,
            to,
            group_by.copy(),
            window_size,
        )
        rows = await self._query(sql)
        return UsageResponse(
            windowSize=window_size,
            data=[
                Usage.from_result(
                    [
                        int((r.get(table.ts_interval) + interval).timestamp()),
                        r.get(table.value_col),
                    ],
                    {**r, "type": table.type} if has_type else r,
                    interval,
                    group_by,
                )
                for r in rows
            ],
            start=from_.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end=to.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    async def query_storage(
        self,
        filtered_by_org_id: list[str] | None,
        filtered_by_proj_id: list[str] | None,
        from_: datetime,
        to: datetime | None,
        group_by: list[str],
        window_size: str,
    ) -> UsageResponse:
        file_table = FileStorageTable()
        db_table = DBStorageTable()
        to = to or datetime.now(timezone.utc)
        group_by = self._process_group_by(group_by)
        # group_by might be modified
        file_sql, _ = _build_time_bucket_query(
            file_table,
            filtered_by_org_id,
            filtered_by_proj_id,
            from_,
            to,
            group_by.copy(),
            window_size,
        )
        file_rows = await self._query(file_sql)
        db_sql, interval = _build_time_bucket_query(
            db_table,
            filtered_by_org_id,
            filtered_by_proj_id,
            from_,
            to,
            group_by.copy(),
            window_size,
        )
        db_rows = await self._query(db_sql)
        if "type" in group_by:  # to be compatible with VM query
            usages = []
            for r in file_rows:
                usages.append(
                    Usage.from_result(
                        [
                            int((r.get(file_table.ts_interval) + interval).timestamp()),
                            r.get(file_table.snapshot_col),
                        ],
                        {**r, "type": file_table.type},
                        interval,
                        group_by,
                    )
                )
            for r in db_rows:
                usages.append(
                    Usage.from_result(
                        [
                            int((r.get(db_table.ts_interval) + interval).timestamp()),
                            r.get(db_table.snapshot_col),
                        ],
                        {**r, "type": db_table.type},
                        interval,
                        group_by,
                    )
                )
        else:
            usages = [
                Usage.from_result(
                    [
                        int((r.get(file_table.ts_interval) + interval).timestamp()),
                        r.get(file_table.snapshot_col),
                    ],
                    r,
                    interval,
                    group_by,
                )
                for r in file_rows
            ] + [
                Usage.from_result(
                    [
                        int((r.get(db_table.ts_interval) + interval).timestamp()),
                        r.get(db_table.snapshot_col),
                    ],
                    r,
                    interval,
                    group_by,
                )
                for r in db_rows
            ]
        return UsageResponse(
            windowSize=window_size,
            data=usages,
            start=from_.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end=to.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    async def query_billing(
        self,
        filtered_by_org_id: list[str] | None,
        filtered_by_proj_id: list[str] | None,
        from_: datetime,
        to: datetime | None,
        group_by: list[str],
        window_size: str,
    ) -> UsageResponse:
        cost_table = CostTable()
        to = to or datetime.now(timezone.utc)
        group_by = list(set([cost_table.org_col] + group_by))
        has_category = "category" in group_by
        has_type = "type" in group_by
        has_model = "model" in group_by
        sql, interval = _build_time_bucket_query(
            cost_table,
            filtered_by_org_id,
            filtered_by_proj_id,
            from_,
            to,
            group_by.copy(),  # group_by might be modified
            window_size,
        )
        rows = await self._query(sql)
        usages = []

        gb_filters = _build_gb_filters(has_category, has_type, has_model)
        active_metrics = _get_active_metrics(has_category, has_type)

        usages: list[Usage] = []
        for row in rows:
            ts = int((row.get(cost_table.ts_interval) + interval).timestamp())
            for metric in active_metrics:
                value = row.get(metric.value_col)
                if value <= 0:
                    continue

                metrics_dict = {
                    **row,
                    **metric.extra_dims,
                }
                usages.append(
                    Usage.from_result(
                        [ts, value],
                        metrics_dict,
                        interval,
                        _filter_groupby(group_by, gb_filters[metric.gb_mask]),
                    )
                )
        return UsageResponse(
            windowSize=window_size,
            data=usages,
            start=from_.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end=to.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
