from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from owl.db import SCHEMA, async_session, cached_text
from owl.types import UsageResponse, UserAuth
from owl.utils.auth import (
    auth_user_service_key,
    has_permissions,
)
from owl.utils.billing import CLICKHOUSE_CLIENT
from owl.utils.billing_metrics import BillingMetrics
from owl.utils.exceptions import (
    BadInputError,
    handle_exception,
)
from owl.utils.metrics import Telemetry

router = APIRouter()
telemetry = Telemetry()

billing_metrics = BillingMetrics(clickhouse_client=CLICKHOUSE_CLIENT)


async def _check_permissions(
    user: UserAuth,
    org_ids: list[str] | None,
    proj_ids: list[str] | None,
) -> None:
    if org_ids is None and proj_ids is None:
        # This will return usages across ALL orgs and ALL projects
        has_permissions(user, ["system.MEMBER"])
    else:
        if org_ids:
            for org_id in org_ids:
                has_permissions(user, ["organization.MEMBER"], organization_id=org_id)
        if proj_ids:
            for proj_id in proj_ids:
                async with async_session() as session:
                    stmt = f"""SELECT organization_id FROM {SCHEMA}."Project" WHERE id = '{proj_id}';"""
                    org_id = (await session.exec(cached_text(stmt))).one()
                has_permissions(
                    user,
                    ["organization.MEMBER", "project.MEMBER"],
                    organization_id=org_id,
                    project_id=proj_id,
                )


@router.get(
    "/v2/meters/usages",
    summary="Get the usage metrics of the specified type (llm, embedding, reranking, image).",
    description=(
        "Permissions: `system.MEMBER` to retrieve metrics for all organizations or all projects; "
        "`organization.MEMBER` to retrieve metrics for a specific organization; "
        "`project.MEMBER` to retrieve metrics for a specific project."
    ),
    response_model=UsageResponse,
)
@handle_exception
async def get_usage_metrics(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    type: Annotated[
        Literal["llm", "embedding", "reranking", "image"],
        Query(
            min_length=1,
            description=(
                "Type of usage data to query. Must be one of: 'llm', 'embedding', 'reranking', "
                "or 'image'."
            ),
        ),
    ],
    from_: Annotated[
        datetime, Query(alias="from", description="Start datetime for the usage data query.")
    ],
    window_size: Annotated[
        str,
        Query(
            min_length=1,
            description="The aggregation window size (e.g., '1d' for daily, '1w' for weekly).",
            alias="windowSize",
        ),
    ],
    org_ids: Annotated[
        list[str] | None,
        Query(
            description="List of organization IDs to filter the query. If not provided, data for all organizations is returned.",
            alias="orgIds",
        ),
    ] = None,
    proj_ids: Annotated[
        list[str] | None,
        Query(
            description="List of project IDs to filter the query. If not provided, data for all projects is returned.",
            alias="projIds",
        ),
    ] = None,
    to: Annotated[
        datetime | None,
        Query(
            description="End datetime for the usage data query. If not provided, data up to the current datetime is returned."
        ),
    ] = None,
    group_by: Annotated[
        list[str] | None,
        Query(
            min_length=1,
            description="List of fields to group the usage data by. If not provided, no grouping is applied.",
            alias="groupBy",
        ),
    ] = None,
    data_source: Annotated[
        Literal["clickhouse", "victoriametrics"],
        Query(description="Data source to query. Defaults to 'clickhouse'.", alias="dataSource"),
    ] = "clickhouse",
) -> UsageResponse:
    """
    Retrieves usages metrics based on the provided filters.
    This endpoint requires `system.MEMBER` permission.

    This endpoint allows querying usage data for specific organizations within a given time range.
    The results can be grouped by specified fields and aggregated using a window size.

    Args:
        user (UserAuth): The authenticated user making the request.
        type (str): Type of usage data to query. One of: llm, embedding, reranking.
        from_ (datetime): The start of the time range for the usage data.
        window_size (str): The size of the time window for aggregating usage data
            (e.g., "1d" for daily, "1w" for weekly).
        org_ids (list[str] | None): A list of organization IDs to filter the usage data.
            If not provided, data for all organizations will be returned.
        proj_ids (list[str] | None): A list of project IDs to filter the usage data.
            If not provided, data for all projects will be returned.
        to (datetime | None): The end of the time range for the usage data.
            If not provided, data up to the current date will be returned.
        group_by (list[str] | None): A list of fields to group the usage data by.
            If not provided, the data will not be grouped.
        data_source (str): The data source to query. Defaults to "clickhouse".

    Returns:
        UsageResponse: A response containing window_size and a list of the usage metrics.

    Raises:
        BadInputError: If the 'type' parameter is invalid (not one of 'llm',
          'embedding', 'reranking', or 'image').
    """
    # RBAC
    await _check_permissions(user, org_ids, proj_ids)
    # Fetch
    if group_by is None:
        group_by = []
    if data_source == "clickhouse":
        metrics_client = billing_metrics
    elif data_source == "victoriametrics":
        metrics_client = telemetry
    if type == "llm":
        return await metrics_client.query_llm_usage(
            org_ids, proj_ids, from_, to, group_by, window_size
        )
    elif type == "embedding":
        return await metrics_client.query_embedding_usage(
            org_ids, proj_ids, from_, to, group_by, window_size
        )
    elif type == "reranking":
        return await metrics_client.query_reranking_usage(
            org_ids, proj_ids, from_, to, group_by, window_size
        )
    elif type == "image":
        return await metrics_client.query_image_usage(
            org_ids, proj_ids, from_, to, group_by, window_size
        )
    raise BadInputError(f"type: {type} invalid. Must be one of: llm, embedding, reranking, image")


@router.get(
    "/v2/meters/billings",
    summary="Get billing metrics.",
    description="Permissions: `system.MEMBER`.",
    response_model=UsageResponse,
)
@handle_exception
async def get_billing_metrics(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    from_: Annotated[
        datetime,
        Query(
            alias="from",
            description="Start datetime for the billing data query.",
        ),
    ],
    window_size: Annotated[
        str,
        Query(
            min_length=1,
            description="The aggregation window size (e.g., '1d' for daily, '1w' for weekly).",
            alias="windowSize",
        ),
    ],
    org_ids: Annotated[
        list[str] | None,
        Query(
            description="List of organization IDs to filter the query. If not provided, data for all organizations is returned.",
            alias="orgIds",
        ),
    ] = None,
    proj_ids: Annotated[
        list[str] | None,
        Query(
            description="List of project IDs to filter the query. If not provided, data for all projects is returned.",
            alias="projIds",
        ),
    ] = None,
    to: Annotated[
        datetime | None,
        Query(
            description="End datetime for the billing data query. If not provided, data up to the current datetime is returned.",
        ),
    ] = None,
    group_by: Annotated[
        list[str] | None,
        Query(
            min_length=1,
            description="List of fields to group the billing data by. If not provided, no grouping is applied.",
            alias="groupBy",
        ),
    ] = None,
    data_source: Annotated[
        Literal["clickhouse", "victoriametrics"],
        Query(description="Data source to query. Defaults to 'clickhouse'.", alias="dataSource"),
    ] = "clickhouse",
) -> UsageResponse:
    """
    Retrieves billing metrics based on the provided filters.
    This endpoint requires `system.MEMBER` permission.

    This endpoint allows querying billing data for specific organizations within a given time range.
    The results can be grouped by specified fields and aggregated using a window size.

    Args:
        user (str): The authenticated user making the request.
        from_ (datetime): The start of the time range for the billing data.
        window_size (str): The size of the time window for aggregating billing data
            (e.g., "1d" for daily, "1w" for weekly).
        org_ids (list[str] | None): A list of organization IDs to filter the billing data.
            If not provided, data for all organizations will be returned.
        proj_ids (list[str] | None): A list of project IDs to filter the billing data.
            If not provided, data for all projects will be returned.
        to (datetime | None): The end of the time range for the billing data.
            If not provided, data up to the current date will be returned.
        group_by (list[str] | None): A list of fields to group the billing data by.
            If not provided, the data will not be grouped.
        data_source (str): The data source to query. Defaults to "clickhouse".

    Returns:
        UsageResponse: A response containing window_size and a list of the billing metrics.
    """
    # RBAC
    await _check_permissions(user, org_ids, proj_ids)
    # Fetch
    if group_by is None:
        group_by = []
    if data_source == "clickhouse":
        metrics_client = billing_metrics
    elif data_source == "victoriametrics":
        metrics_client = telemetry
    return await metrics_client.query_billing(org_ids, proj_ids, from_, to, group_by, window_size)


@router.get(
    "/v2/meters/bandwidths",
    summary="Get bandwidth usage metrics.",
    description="Permissions: `system.MEMBER`.",
    response_model=UsageResponse,
)
@handle_exception
async def get_bandwidth_metrics(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    from_: Annotated[
        datetime,
        Query(
            alias="from",
            description="Start datetime for the bandwidth data query.",
        ),
    ],
    window_size: Annotated[
        str,
        Query(
            min_length=1,
            description="The aggregation window size (e.g., '1d' for daily, '1w' for weekly).",
            alias="windowSize",
        ),
    ],
    org_ids: Annotated[
        list[str] | None,
        Query(
            description="List of organization IDs to filter the query. If not provided, data for all organizations is returned.",
            alias="orgIds",
        ),
    ] = None,
    proj_ids: Annotated[
        list[str] | None,
        Query(
            description="List of project IDs to filter the query. If not provided, data for all projects is returned.",
            alias="projIds",
        ),
    ] = None,
    to: Annotated[
        datetime | None,
        Query(
            description="End datetime for the bandwidth data query. If not provided, data up to the current datetime is returned.",
        ),
    ] = None,
    group_by: Annotated[
        list[str] | None,
        Query(
            min_length=1,
            description="List of fields to group the bandwidth data by. If not provided, no grouping is applied.",
            alias="groupBy",
        ),
    ] = None,
    data_source: Annotated[
        Literal["clickhouse", "victoriametrics"],
        Query(description="Data source to query. Defaults to 'clickhouse'.", alias="dataSource"),
    ] = "clickhouse",
) -> UsageResponse:
    """
    Retrieves bandwidth metrics based on the provided filters.
    This endpoint requires `system.MEMBER` permission.

    This endpoint allows querying bandwidth data for specific organizations within a given time range.
    The results can be grouped by specified fields and aggregated using a window size.

    Args:
        user (str): The authenticated user making the request.
        from_ (datetime): The start of the time range for the bandwidth data.
        window_size (str): The size of the time window for aggregating bandwidth data
            (e.g., "1d" for daily, "1w" for weekly).
        org_ids (list[str] | None): A list of organization IDs to filter the bandwidth data.
            If not provided, data for all organizations will be returned.
        proj_ids (list[str] | None): A list of project IDs to filter the bandwidth data.
            If not provided, data for all projects will be returned.
        to (datetime | None): The end of the time range for the bandwidth data.
            If not provided, data up to the current date will be returned.
        group_by (list[str] | None): A list of fields to group the bandwidth data by.
            If not provided, the data will not be grouped.
        data_source (str): The data source to query. Defaults to "clickhouse".

    Returns:
        UsageResponse: A response containing window_size and a list of the bandwidth metrics.
    """
    # RBAC
    await _check_permissions(user, org_ids, proj_ids)
    # Fetch
    if group_by is None:
        group_by = []
    if data_source == "clickhouse":
        metrics_client = billing_metrics
    elif data_source == "victoriametrics":
        metrics_client = telemetry
    return await metrics_client.query_bandwidth(
        org_ids, proj_ids, from_, to, group_by, window_size
    )


@router.get(
    "/v2/meters/storages",
    summary="Get storage usage metrics.",
    description="Permissions: `system.MEMBER`.",
    response_model=UsageResponse,
)
@handle_exception
async def get_storage_metrics(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    from_: Annotated[
        datetime,
        Query(
            alias="from",
            description="Start datetime for the storage data query.",
        ),
    ],
    window_size: Annotated[
        str,
        Query(
            min_length=1,
            description="The aggregation window size (e.g., '1d' for daily, '1w' for weekly).",
            alias="windowSize",
        ),
    ],
    org_ids: Annotated[
        list[str] | None,
        Query(
            description="List of organization IDs to filter the query. If not provided, data for all organizations is returned.",
            alias="orgIds",
        ),
    ] = None,
    proj_ids: Annotated[
        list[str] | None,
        Query(
            description="List of project IDs to filter the query. If not provided, data for all projects is returned.",
            alias="projIds",
        ),
    ] = None,
    to: Annotated[
        datetime | None,
        Query(
            description="End datetime for the storage data query. If not provided, data up to the current datetime is returned.",
        ),
    ] = None,
    group_by: Annotated[
        list[str] | None,
        Query(
            min_length=1,
            description="List of fields to group the storage data by. If not provided, no grouping is applied.",
            alias="groupBy",
        ),
    ] = None,
    data_source: Annotated[
        Literal["clickhouse", "victoriametrics"],
        Query(description="Data source to query. Defaults to 'clickhouse'.", alias="dataSource"),
    ] = "clickhouse",
) -> UsageResponse:
    """
    Retrieves storage metrics based on the provided filters.
    This endpoint requires `system.MEMBER` permission.

    This endpoint allows querying storage data for specific organizations within a given time range.
    The results can be grouped by specified fields and aggregated using a window size.

    Args:
        user (str): The authenticated user making the request.
        from_ (datetime): The start of the time range for the storage data.
        window_size (str): The size of the time window for aggregating storage data
            (e.g., "1d" for daily, "1w" for weekly).
        org_ids (list[str] | None): A list of organization IDs to filter the storage data.
            If not provided, data for all organizations will be returned.
        proj_ids (list[str] | None): A list of project IDs to filter the storage data.
            If not provided, data for all projects will be returned.
        to (datetime | None): The end of the time range for the storage data.
            If not provided, data up to the current date will be returned.
        group_by (list[str] | None): A list of fields to group the storage data by.
            If not provided, the data will not be grouped.

    Returns:
        UsageResponse: A response containing window_size and a list of the storage metrics.
    """
    # RBAC
    await _check_permissions(user, org_ids, proj_ids)
    # Fetch
    if group_by is None:
        group_by = []
    if data_source == "clickhouse":
        metrics_client = billing_metrics
    elif data_source == "victoriametrics":
        metrics_client = telemetry
    return await metrics_client.query_storage(org_ids, proj_ids, from_, to, group_by, window_size)


# @router.get(
#     "/v2/meters/models/throughput",
#     summary="Get the model throughput statistics of the specified model type (llm, embedding, reranking), and metric type.",
#     description="Permissions: `system.models` OR `system.metrics`.",
#     response_model=UsageResponse,
# )
# @handle_exception
# async def get_model_throughput_metrics(
#     user: Annotated[UserAuth, Depends(auth_user_service_key)],
#     type: Annotated[
#         Literal["llm", "embedding", "reranking"],
#         Query(
#             min_length=1,
#             description="Type of usage data to query. Must be one of: 'llm', 'embedding', or 'reranking'.",
#         ),
#     ],
#     metric_type: Annotated[
#         Literal["tpm", "rpm", "spm"],
#         Query(
#             min_length=1,
#             description=(
#                 "Type of metric to query, "
#                 "Here is the list of possible metric type: "
#                 "llm: tpm, rpm"
#                 "embedding: tpm, rpm"
#                 "reranking: spm, rpm"
#                 "tpm (tokens per minute), rpm (requests per minute), spm (searches per minute) "
#             ),
#         ),
#     ],
#     from_: Annotated[
#         datetime, Query(alias="from", description="Start datetime for the usage data query.")
#     ],
#     to: Annotated[
#         datetime | None,
#         Query(
#             description="End datetime for the usage data query. If not provided, data up to the current datetime is returned."
#         ),
#     ] = None,
# ) -> UsageResponse:
#     """
#     Retrieves model throughput statistics based on the provided filters.
#     This endpoint requires `system.metrics` permission.

#     This endpoint allows querying model throughput statistics data for specific metric type within a given time range.

#     Args:
#         user (UserAuth): The authenticated user making the request.
#         type (str): Type of usage data to query. One of: llm, embedding, reranking.
#         metric_type (str): Type of metric to query. One of tpm, rpm, spm.
#             Valid metric_type depends on model type:
#             llm: tpm, rpm
#             embedding: tpm, rpm
#             reranking: spm, rpm
#         from_ (datetime): The start of the time range for the usage data.
#         to (datetime | None): The end of the time range for the usage data.
#             If not provided, data up to the current date will be returned.

#     Returns:
#         UsageResponse: A response containing window_size and a list of the usage metrics.

#     Raises:
#         BadInputError: If the 'type' parameter is invalid (not one of 'llm',
#           'embedding', or 'reranking'). Or if the 'model_type' parameter is invalid.
#     """
#     has_permissions(user, ["system.models", "system.metrics"])
#     if type == "llm":
#         if metric_type == "tpm":
#             return await telemetry.query_llm_tpm(from_, to)
#         elif metric_type == "rpm":
#             return await telemetry.query_llm_rpm(from_, to)
#     elif type == "embedding":
#         if metric_type == "tpm":
#             return await telemetry.query_embed_tpm(from_, to)
#         elif metric_type == "rpm":
#             return await telemetry.query_embed_rpm(from_, to)
#     elif type == "reranking":
#         if metric_type == "spm":
#             return await telemetry.query_rerank_spm(from_, to)
#         elif metric_type == "rpm":
#             return await telemetry.query_rerank_rpm(from_, to)
#     raise BadInputError(
#         f"type: {type} with metric type: {metric_type} invalid. Must be one of: llm (tpm, rpm), embedding (tpm, rpm), reranking (tpm, rpm)"
#     )


# @router.get(
#     "/v2/meters/models/latency",
#     summary="Get the model latency past hour statistics of the specified model type (llm, embedding, reranking), and metric type.",
#     description="Permissions: `system.models` OR `system.metrics`.",
#     response_model=UsageResponse,
# )
# @handle_exception
# async def get_model_latency_metrics(
#     user: Annotated[UserAuth, Depends(auth_user_service_key)],
#     type: Annotated[
#         Literal["llm", "embedding", "reranking"],
#         Query(
#             min_length=1,
#             description="Type of usage data to query. Must be one of: 'llm', 'embedding', or 'reranking'.",
#         ),
#     ],
#     metric_type: Annotated[
#         Literal["itl", "ttft", "tpot", "rt"],
#         Query(
#             min_length=1,
#             description=(
#                 "Type of metric to query, "
#                 "Here is the list of possible metric type: "
#                 "llm: itl, ttft, tpot "
#                 "embedding: rt "
#                 "reranking: rt "
#                 "itl (inter-token latency), ttft (time to first token), tpot (time per output token), rt (response time)"
#             ),
#         ),
#     ],
#     quantile: Annotated[
#         float,
#         Query(
#             ge=0,
#             le=1,
#             description=("Quantile of latency to query, ex: 0.95 means 95th percentile latency."),
#         ),
#     ],
#     from_: Annotated[
#         datetime, Query(alias="from", description="Start datetime for the usage data query.")
#     ],
#     to: Annotated[
#         datetime | None,
#         Query(
#             description="End datetime for the usage data query. If not provided, data up to the current datetime is returned."
#         ),
#     ] = None,
# ) -> UsageResponse:
#     """
#     Retrieves model latency statistics based on the provided filters.
#     This endpoint requires `system.metrics` permission.

#     This endpoint allows querying model latency statistics data for specific metric type within a given time range.

#     Args:
#         user (UserAuth): The authenticated user making the request.
#         type (str): Type of usage data to query. One of: llm, embedding, reranking.
#         metric_type (str): Type of metric to query. One of ttft, tpot, rt.
#             Valid metric_type depends on model type:
#             llm: itl, ttft, tpot
#             embedding: rt
#             reranking: rt
#         quantile (float): Quantile of latency to query, ex: 0.95 means 95th percentile latency.
#         from_ (datetime): The start of the time range for the usage data.
#         to (datetime | None): The end of the time range for the usage data.
#             If not provided, data up to the current date will be returned.

#     Returns:
#         Each data point is the quantile latency based on past 1 hour data, with 1 minute resolution.
#         UsageResponse: A response containing window_size and a list of the usage metrics.

#     Raises:
#         BadInputError: If the 'type' parameter is invalid (not one of 'llm',
#           'embedding', or 'reranking'). Or if the 'model_type' parameter is invalid.
#     """
#     has_permissions(user, ["system.models", "system.metrics"])
#     if type == "llm":
#         if metric_type == "ttft":
#             return await telemetry.query_hourly_llm_ttft_quantile(from_, to, quantile)
#         elif metric_type == "tpot":
#             return await telemetry.query_hourly_llm_tpot_quantile(from_, to, quantile)
#         elif metric_type == "itl":
#             return await telemetry.query_hourly_llm_itl_quantile(from_, to, quantile)
#     elif type == "embedding":
#         if metric_type == "rt":
#             return await telemetry.query_hourly_embed_completion_time_quantile(from_, to, quantile)
#     elif type == "reranking":
#         if metric_type == "rt":
#             return await telemetry.query_hourly_rerank_completion_time_quantile(
#                 from_, to, quantile
#             )
#     raise BadInputError(
#         f"type: {type} with metric type: {metric_type} invalid. Must be one of: llm (itl, ttft, tpot), embedding (rt), reranking (rt)"
#     )
