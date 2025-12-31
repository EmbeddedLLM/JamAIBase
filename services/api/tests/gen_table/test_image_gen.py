from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from os.path import dirname, join, realpath
from time import sleep

import httpx
import pytest
from flaky import flaky

from jamaibase import JamAI
from jamaibase.types import (
    ColumnSchemaCreate,
    DeploymentCreate,
    GetURLResponse,
    ImageGenConfig,
    ModelConfigCreate,
    OrganizationCreate,
)
from owl.configs import ENV_CONFIG
from owl.types import CloudProvider, ModelCapability, ModelType, Role, TableType
from owl.utils import uuid7_str
from owl.utils.test import (
    DS_PARAMS,
    STREAM_PARAMS,
    add_table_rows,
    create_organization,
    create_project,
    create_table,
    create_user,
    get_file_map,
    list_table_rows,
    upload_file,
)

TEST_FILE_DIR = join(dirname(dirname(realpath(__file__))), "files")
FILES = get_file_map(TEST_FILE_DIR)

METER_RETRY = 50
METER_RETRY_DELAY = 1


@dataclass(slots=True)
class MockImageMetricsContext:
    superuser_id: str
    user_id: str
    org_id: str
    project_id: str
    image_model_id: str
    image_costs: dict[str, float]
    image_uri: str


@dataclass(slots=True)
class RealImageMetricsContext:
    superuser_id: str
    user_id: str
    org_id: str
    project_id: str
    openai_model_id: str
    gemini_model_id: str


@dataclass(slots=True)
class ImageMetricsSetup:
    mock: MockImageMetricsContext
    real: RealImageMetricsContext


@dataclass(slots=True)
class ImageRunContext:
    start_dt: datetime
    end_dt: datetime
    prompt_value: str
    expected_counts: dict[str, int] | None
    expected_costs: dict[str, float] | None


def _prompt_tokens(prompt: str) -> int:
    return max(1, len(prompt.split())) if isinstance(prompt, str) else 1


def _metrics_match_image_token_counts(metrics_data: dict, serving_info: dict) -> bool:
    expected = serving_info["expected_counts"]
    model_id = serving_info["model"]
    totals: dict[str, float] = {k: 0.0 for k in expected.keys()}
    for entry in metrics_data.get("data", []):
        if entry["groupBy"].get("model", "") != model_id:
            continue
        entry_type = entry["groupBy"].get("type")
        if entry_type in expected:
            totals[entry_type] += entry["value"]
    return all(totals[key] == expected[key] for key in expected.keys())


def _metrics_match_image_spent(metrics_data: dict, serving_info: dict) -> bool:
    expected = serving_info["expected_costs"]
    model_id = serving_info["model"]
    totals: dict[str, float] = {k: 0.0 for k in expected.keys()}
    for entry in metrics_data.get("data", []):
        if (
            entry["groupBy"].get("model", "") != model_id
            or entry["groupBy"].get("category", "") != "image_tokens"
        ):
            continue
        entry_type = entry["groupBy"].get("type")
        if entry_type in expected:
            totals[entry_type] += entry["value"]
    return all(round(totals[key], 8) == expected[key] for key in expected.keys())


@pytest.fixture(scope="module")
def image_setup() -> ImageMetricsSetup:
    with (
        create_user() as superuser,
        create_user({"email": "testuser@example.com", "name": "Test User"}) as mock_user,
        create_user({"email": "realuser@example.com", "name": "Real User"}) as real_user,
        create_organization(
            body=OrganizationCreate(name="Image Metrics Org"), user_id=superuser.id
        ) as mock_org,
        create_project(
            dict(name="Image Metrics Project"),
            user_id=superuser.id,
            organization_id=mock_org.id,
        ) as mock_project,
        create_organization(
            body=OrganizationCreate(name="Image Real Org"), user_id=real_user.id
        ) as real_org,
        create_project(
            dict(name="Image Real Project"),
            user_id=real_user.id,
            organization_id=real_org.id,
        ) as real_project,
    ):
        admin_client = JamAI(user_id=superuser.id)
        admin_client.organizations.join_organization(
            user_id=mock_user.id, organization_id=mock_org.id, role=Role.ADMIN
        )
        admin_client.projects.join_project(
            user_id=mock_user.id, project_id=mock_project.id, role=Role.ADMIN
        )

        image_model_id = f"openai/mock-image-gen-{uuid7_str()}"
        image_costs = {
            "text_input": 0.01,
            "text_output": 0.01,
            "image_input": 0.01,
            "image_output": 0.01,
        }
        openai_model_id = f"openai/gpt-image-1.5-test-{uuid7_str()}"
        gemini_model_id = f"gemini/gemini-2.5-image-test-{uuid7_str()}"

        model_client = JamAI(user_id=superuser.id, token=ENV_CONFIG.service_key_plain)
        image_model = model_client.models.create_model_config(
            ModelConfigCreate(
                id=image_model_id,
                type=ModelType.IMAGE_GEN,
                name="Mock Image Gen Model",
                capabilities=[ModelCapability.IMAGE_OUT, ModelCapability.IMAGE],
                context_length=8192,
                languages=["en"],
                owned_by="openai",
                llm_input_cost_per_mtoken=image_costs["text_input"],
                llm_output_cost_per_mtoken=image_costs["text_output"],
                image_input_cost_per_mtoken=image_costs["image_input"],
                image_output_cost_per_mtoken=image_costs["image_output"],
            )
        )
        model_client.models.create_deployment(
            DeploymentCreate(
                model_id=image_model.id,
                name="Mock Image Gen Deployment",
                provider=CloudProvider.ELLM,
                routing_id=image_model.id,
                api_base=ENV_CONFIG.test_llm_api_base,
            )
        )
        openai_model = model_client.models.create_model_config(
            ModelConfigCreate(
                id=openai_model_id,
                type=ModelType.IMAGE_GEN,
                name="OpenAI Image Gen Model",
                capabilities=[ModelCapability.IMAGE_OUT, ModelCapability.IMAGE],
                context_length=200000,
                languages=["en"],
                llm_input_cost_per_mtoken=5.0,
                llm_output_cost_per_mtoken=10.0,
                image_input_cost_per_mtoken=8.0,
                image_output_cost_per_mtoken=32.0,
            )
        )
        gemini_model = model_client.models.create_model_config(
            ModelConfigCreate(
                id=gemini_model_id,
                type=ModelType.IMAGE_GEN,
                name="Gemini Image Gen Model",
                capabilities=[ModelCapability.IMAGE_OUT],
                context_length=65536,
                languages=["en"],
                llm_input_cost_per_mtoken=0.3,
                llm_output_cost_per_mtoken=0.0,
                image_input_cost_per_mtoken=0.0,
                image_output_cost_per_mtoken=30.0,
            )
        )
        model_client.models.create_deployment(
            DeploymentCreate(
                model_id=openai_model.id,
                name="OpenAI Image Gen Deployment",
                provider=CloudProvider.OPENAI,
                routing_id="openai/gpt-image-1.5",
            )
        )
        model_client.models.create_deployment(
            DeploymentCreate(
                model_id=gemini_model.id,
                name="Gemini Image Gen Deployment",
                provider=CloudProvider.GEMINI,
                routing_id="gemini/gemini-2.5-flash-image",
            )
        )
        image_uri = upload_file(
            JamAI(user_id=superuser.id, project_id=mock_project.id),
            FILES["rabbit.jpeg"],
        ).uri

        yield ImageMetricsSetup(
            mock=MockImageMetricsContext(
                superuser_id=superuser.id,
                user_id=mock_user.id,
                org_id=mock_org.id,
                project_id=mock_project.id,
                image_model_id=image_model.id,
                image_costs=image_costs,
                image_uri=image_uri,
            ),
            real=RealImageMetricsContext(
                superuser_id=superuser.id,
                user_id=real_user.id,
                org_id=real_org.id,
                project_id=real_project.id,
                openai_model_id=openai_model.id,
                gemini_model_id=gemini_model.id,
            ),
        )


@pytest.fixture(scope="module")
def mock_setup(image_setup: ImageMetricsSetup) -> MockImageMetricsContext:
    return image_setup.mock


@pytest.fixture(scope="module")
def real_setup(image_setup: ImageMetricsSetup) -> RealImageMetricsContext:
    return image_setup.real


@pytest.fixture(scope="module")
def mock_run(mock_setup: MockImageMetricsContext) -> ImageRunContext:
    client = JamAI(user_id=mock_setup.user_id, project_id=mock_setup.project_id)
    prompt_value = "red square"
    start_dt = datetime.now(tz=timezone.utc)

    cols = [
        ColumnSchemaCreate(id="prompt", dtype="str"),
        ColumnSchemaCreate(id="source_image", dtype="image"),
        ColumnSchemaCreate(
            id="image_gen",
            dtype="image",
            gen_config=ImageGenConfig(
                model=mock_setup.image_model_id,
                prompt="Generate ${prompt}",
                size="1024x1024",
            ),
        ),
        ColumnSchemaCreate(
            id="image_edit",
            dtype="image",
            gen_config=ImageGenConfig(
                model=mock_setup.image_model_id,
                prompt="Edit ${source_image} with ${prompt}",
                size="1024x1024",
            ),
        ),
        ColumnSchemaCreate(
            id="image_edit_2",
            dtype="image",
            gen_config=ImageGenConfig(
                model=mock_setup.image_model_id,
                prompt="Edit ${source_image} with ${prompt}",
                size="1024x1024",
            ),
        ),
    ]

    with create_table(client, TableType.ACTION, cols=cols) as table:
        add_table_rows(
            client,
            TableType.ACTION,
            table.id,
            [{"prompt": prompt_value, "source_image": mock_setup.image_uri}],
            stream=False,
            check_usage=False,
        )
    end_dt = datetime.now(tz=timezone.utc)
    if end_dt < start_dt + timedelta(seconds=20):
        end_dt = start_dt + timedelta(seconds=20)

    text_in_gen = _prompt_tokens(f"Generate {prompt_value}")
    text_in_edit = _prompt_tokens(f"Edit with {prompt_value}")
    expected_counts = {
        "text_input": text_in_gen + (text_in_edit * 2),
        "text_output": 0,
        "image_input": 2,
        "image_output": 3,
    }
    expected_costs = {
        "text_input": round(
            expected_counts["text_input"] * 1e-6 * mock_setup.image_costs["text_input"],
            8,
        ),
        "text_output": 0.0,
        "image_input": round(
            expected_counts["image_input"] * 1e-6 * mock_setup.image_costs["image_input"],
            8,
        ),
        "image_output": round(
            expected_counts["image_output"] * 1e-6 * mock_setup.image_costs["image_output"],
            8,
        ),
    }
    return ImageRunContext(
        start_dt=start_dt,
        end_dt=end_dt,
        prompt_value=prompt_value,
        expected_counts=expected_counts,
        expected_costs=expected_costs,
    )


@pytest.mark.parametrize("stream", **STREAM_PARAMS)
async def test_image_output_column_gen_and_edit(
    mock_setup: MockImageMetricsContext,
    stream: bool,
):
    table_type = TableType.ACTION
    client = JamAI(user_id=mock_setup.superuser_id, project_id=mock_setup.project_id)
    image_model_id = f"openai/mock-image-output-{uuid7_str()}"
    cols = [
        ColumnSchemaCreate(id="prompt", dtype="str"),
        ColumnSchemaCreate(id="source_image", dtype="image"),
        ColumnSchemaCreate(
            id="image_gen",
            dtype="image",
            gen_config=ImageGenConfig(
                model=image_model_id,
                prompt="Generate an image for ${prompt}",
                size="1024x1024",
            ),
        ),
        ColumnSchemaCreate(
            id="image_edit",
            dtype="image",
            gen_config=ImageGenConfig(
                model=image_model_id,
                prompt="Edit ${source_image} with ${prompt}",
                size="1024x1024",
            ),
        ),
    ]

    model_client = JamAI(user_id=mock_setup.superuser_id, token=ENV_CONFIG.service_key_plain)
    image_model = model_client.models.create_model_config(
        ModelConfigCreate(
            id=image_model_id,
            type=ModelType.IMAGE_GEN,
            name="Mock Image Output Model",
            capabilities=[ModelCapability.IMAGE_OUT, ModelCapability.IMAGE],
            context_length=8192,
            languages=["en"],
            owned_by="openai",
            llm_input_cost_per_mtoken=mock_setup.image_costs["text_input"],
            llm_output_cost_per_mtoken=mock_setup.image_costs["text_output"],
            image_input_cost_per_mtoken=mock_setup.image_costs["image_input"],
            image_output_cost_per_mtoken=mock_setup.image_costs["image_output"],
        )
    )
    model_client.models.create_deployment(
        DeploymentCreate(
            model_id=image_model.id,
            name="Mock Image Output Deployment",
            provider=CloudProvider.ELLM,
            routing_id=image_model.id,
            api_base=ENV_CONFIG.test_llm_api_base,
        )
    )
    with create_table(client, table_type, cols=cols) as table:
        image_uri = upload_file(client, FILES["rabbit.jpeg"]).uri
        response = add_table_rows(
            client,
            table_type,
            table.id,
            [{"prompt": "a red square", "source_image": image_uri}],
            stream=stream,
            check_usage=False,
        )
        assert len(response.rows) == 1
        for col_id in ("image_gen", "image_edit"):
            assert response.rows[0].columns[col_id].content.startswith(("file://", "s3://"))
            usage = response.rows[0].columns[col_id].usage
            assert usage is not None
            assert usage.prompt_tokens_details is not None
            assert usage.completion_tokens_details is not None
            assert usage.prompt_tokens_details.text_tokens >= 1
            assert usage.prompt_tokens_details.image_tokens >= 0
            assert usage.completion_tokens_details.image_tokens >= 1
            assert usage.completion_tokens_details.reasoning_tokens >= 0

        rows = list_table_rows(client, table_type, table.id)
        row = rows.values[0]
        for col_id in ("image_gen", "image_edit"):
            file_uri = row[col_id]
            assert isinstance(file_uri, str)
            assert file_uri.startswith(("file://", "s3://"))
            assert file_uri.endswith(".png")
            url_response = client.file.get_raw_urls([file_uri])
            assert isinstance(url_response, GetURLResponse)
            content = httpx.get(url_response.urls[0]).content
            assert content.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.fixture(scope="module")
def real_run(real_setup: RealImageMetricsContext) -> ImageRunContext:
    client = JamAI(user_id=real_setup.user_id, project_id=real_setup.project_id)
    prompt_value = "red square"
    start_dt = datetime.now(tz=timezone.utc)

    cols = [
        ColumnSchemaCreate(id="prompt", dtype="str"),
        ColumnSchemaCreate(
            id="image_openai",
            dtype="image",
            gen_config=ImageGenConfig(
                model=real_setup.openai_model_id,
                prompt="Generate ${prompt}",
                size="1024x1024",
            ),
        ),
        ColumnSchemaCreate(
            id="image_gemini",
            dtype="image",
            gen_config=ImageGenConfig(
                model=real_setup.gemini_model_id,
                prompt="Generate ${prompt}",
                size="1024x1024",
            ),
        ),
    ]

    with create_table(client, TableType.ACTION, cols=cols) as table:
        add_table_rows(
            client,
            TableType.ACTION,
            table.id,
            [{"prompt": prompt_value}],
            stream=False,
            check_usage=False,
        )
    end_dt = datetime.now(tz=timezone.utc)
    if end_dt < start_dt + timedelta(seconds=20):
        end_dt = start_dt + timedelta(seconds=20)

    return ImageRunContext(
        start_dt=start_dt,
        end_dt=end_dt,
        prompt_value=prompt_value,
        expected_counts=None,
        expected_costs=None,
    )


@pytest.mark.cloud
@pytest.mark.parametrize("data_source", **DS_PARAMS)
def test_image_usage_metrics_mock(
    mock_setup: MockImageMetricsContext, mock_run: ImageRunContext, data_source: str
):
    client = JamAI(user_id=mock_setup.user_id, project_id=mock_setup.project_id)
    serving_info = {
        "model": mock_setup.image_model_id,
        "expected_counts": mock_run.expected_counts,
    }

    response_match = False
    for _ in range(METER_RETRY):
        response = client.meters.get_usage_metrics(
            type="image",
            from_=mock_run.start_dt,
            to=mock_run.end_dt,
            window_size="10s",
            proj_ids=[mock_setup.project_id],
            group_by=["type", "model"],
            data_source=data_source,
        )
        print(f"8484: {response.model_dump()=}")
        if _metrics_match_image_token_counts(response.model_dump(), serving_info):
            response_match = True
            break
        sleep(METER_RETRY_DELAY)
    assert response_match

    org_response = client.organizations.get_organization_metrics(
        metric_id="image",
        from_=mock_run.start_dt,
        to=mock_run.end_dt,
        window_size="10s",
        org_id=mock_setup.org_id,
        proj_ids=[mock_setup.project_id],
        group_by=["type", "model"],
        data_source=data_source,
    )
    assert _metrics_match_image_token_counts(org_response.model_dump(), serving_info)

    total_expected = sum(mock_run.expected_counts.values())
    total_match = False
    for _ in range(METER_RETRY):
        response = client.meters.get_usage_metrics(
            type="image",
            from_=mock_run.start_dt,
            to=mock_run.end_dt,
            window_size="10s",
            proj_ids=[mock_setup.project_id],
            group_by=["model"],
            data_source=data_source,
        )
        values = [
            entry["value"]
            for entry in response.model_dump().get("data", [])
            if entry["groupBy"].get("model") == mock_setup.image_model_id
        ]
        if values and sum(values) == total_expected:
            total_match = True
            break
        sleep(METER_RETRY_DELAY)
    assert total_match

    llm_response = client.meters.get_usage_metrics(
        type="llm",
        from_=mock_run.start_dt,
        to=mock_run.end_dt,
        window_size="10s",
        proj_ids=[mock_setup.project_id],
        group_by=["model"],
        data_source=data_source,
    )
    assert all(
        entry["groupBy"].get("model") != mock_setup.image_model_id
        for entry in llm_response.model_dump().get("data", [])
    )


@pytest.mark.cloud
@flaky(max_runs=5, min_passes=1)
@pytest.mark.parametrize("data_source", **DS_PARAMS)
def test_image_billing_metrics_mock(
    mock_setup: MockImageMetricsContext, mock_run: ImageRunContext, data_source: str
):
    client = JamAI(user_id=mock_setup.user_id, project_id=mock_setup.project_id)
    serving_info = {
        "model": mock_setup.image_model_id,
        "expected_costs": mock_run.expected_costs,
    }

    response_match = False
    for _ in range(METER_RETRY):
        response = client.meters.get_billing_metrics(
            from_=mock_run.start_dt,
            to=mock_run.end_dt,
            window_size="10s",
            proj_ids=[mock_setup.project_id],
            group_by=["type", "model", "category"],
            data_source=data_source,
        )
        if _metrics_match_image_spent(response.model_dump(), serving_info):
            response_match = True
            break
        sleep(METER_RETRY_DELAY)
    assert response_match

    org_response = client.organizations.get_organization_metrics(
        metric_id="spent",
        from_=mock_run.start_dt,
        to=mock_run.end_dt,
        window_size="10s",
        org_id=mock_setup.org_id,
        proj_ids=[mock_setup.project_id],
        group_by=["type", "model", "category"],
        data_source=data_source,
    )
    assert _metrics_match_image_spent(org_response.model_dump(), serving_info)


@pytest.mark.cloud
@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("data_source", **DS_PARAMS)
def test_image_usage_metrics_real(
    real_setup: RealImageMetricsContext, real_run: ImageRunContext, data_source: str
):
    client = JamAI(user_id=real_setup.user_id, project_id=real_setup.project_id)
    for model_id in (real_setup.openai_model_id, real_setup.gemini_model_id):
        response_match = False
        for _ in range(METER_RETRY):
            response = client.meters.get_usage_metrics(
                type="image",
                from_=real_run.start_dt,
                to=real_run.end_dt,
                window_size="10s",
                proj_ids=[real_setup.project_id],
                group_by=["model"],
                data_source=data_source,
            )
            values = [
                entry["value"]
                for entry in response.model_dump().get("data", [])
                if entry["groupBy"].get("model") == model_id
            ]
            if values and any(v > 0 for v in values):
                response_match = True
                break
            sleep(METER_RETRY_DELAY)
        assert response_match


@pytest.mark.cloud
@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("data_source", **DS_PARAMS)
def test_image_billing_metrics_real(
    real_setup: RealImageMetricsContext, real_run: ImageRunContext, data_source: str
):
    client = JamAI(user_id=real_setup.user_id, project_id=real_setup.project_id)
    for model_id in (real_setup.openai_model_id, real_setup.gemini_model_id):
        response_match = False
        for _ in range(METER_RETRY):
            response = client.meters.get_billing_metrics(
                from_=real_run.start_dt,
                to=real_run.end_dt,
                window_size="10s",
                proj_ids=[real_setup.project_id],
                group_by=["type", "model", "category"],
                data_source=data_source,
            )
            values = [
                entry["value"]
                for entry in response.model_dump().get("data", [])
                if entry["groupBy"].get("model") == model_id
                and entry["groupBy"].get("category") == "image_tokens"
            ]
            if values and any(v > 0 for v in values):
                response_match = True
                break
            sleep(METER_RETRY_DELAY)
        assert response_match
