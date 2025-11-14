from dataclasses import dataclass
from os.path import dirname, join, realpath

import pytest

from jamaibase import JamAI
from jamaibase.types import (
    OrganizationCreate,
    Page,
    ProjectCreate,
    ProjectRead,
    TableImportRequest,
    TableMetaResponse,
)
from owl.db import TEMPLATE_ORG_ID
from owl.types import Role, TableType
from owl.utils.test import (
    ELLM_DESCRIBE_CONFIG,
    ELLM_DESCRIBE_DEPLOYMENT,
    TEXT_EMBEDDING_3_SMALL_CONFIG,
    TEXT_EMBEDDING_3_SMALL_DEPLOYMENT,
    RERANK_ENGLISH_v3_SMALL_CONFIG,
    RERANK_ENGLISH_v3_SMALL_DEPLOYMENT,
    add_table_rows,
    create_deployment,
    create_model_config,
    create_organization,
    create_project,
    create_user,
    get_file_map,
    upload_file,
)

TEST_FILE_DIR = join(dirname(dirname(realpath(__file__))), "files")
FILES = get_file_map(TEST_FILE_DIR)


def _create_template(client: JamAI, name: str = "Template") -> ProjectRead:
    return client.projects.create_project(
        ProjectCreate(organization_id=TEMPLATE_ORG_ID, name=name)
    )


# We test template creation just as sanity check
# Template creation, update, deletion operations are the same as projects
def test_create_template():
    with create_user() as superuser, create_organization(user_id=superuser.id) as superorg:
        assert superorg.id == "0"
        client = JamAI(user_id=superuser.id)
        template = _create_template(client, "Template 1")
        try:
            assert isinstance(template, ProjectRead)
            assert template.created_by == superuser.id, f"{template.created_by=}, {superuser.id=}"
            assert template.name == "Template 1"
            assert template.organization_id == TEMPLATE_ORG_ID
            # Check memberships
            user = client.users.get_user(superuser.id)
            assert len(user.org_memberships) == 2  # Superorg + Template
            org_memberships = {m.organization_id: m for m in user.org_memberships}
            assert "0" in org_memberships
            assert org_memberships["0"].role == Role.ADMIN
            assert TEMPLATE_ORG_ID in org_memberships
            assert org_memberships[TEMPLATE_ORG_ID].role == Role.ADMIN
            proj_memberships = {m.project_id: m for m in user.proj_memberships}
            assert proj_memberships[template.id].role == Role.ADMIN
        finally:
            client.projects.delete_project(template.id)


@dataclass(slots=True)
class ServingContext:
    superuser_id: str
    superorg_id: str
    project_id: str
    embedding_size: int
    image_uri: str
    audio_uri: str
    document_uri: str
    chat_model_id: str
    embed_model_id: str
    rerank_model_id: str


@pytest.fixture(scope="module")
def setup():
    """
    Fixture to set up the necessary organization and projects for file tests.
    """
    with (
        create_user(dict(email="admin@up.com", name="System Admin")) as superuser,
        create_organization(
            body=OrganizationCreate(name="Superorg"), user_id=superuser.id
        ) as superorg,
        create_project(
            dict(name="Superorg Project"), user_id=superuser.id, organization_id=superorg.id
        ) as p0,
    ):
        assert superuser.id == "0"
        assert superorg.id == "0"

        bge = "ellm/BAAI/bge-m3"
        with (
            # Create models
            create_model_config(ELLM_DESCRIBE_CONFIG) as desc_llm_config,
            create_model_config(TEXT_EMBEDDING_3_SMALL_CONFIG) as embed_config,
            create_model_config(RERANK_ENGLISH_v3_SMALL_CONFIG) as rerank_config,
            create_model_config(
                TEXT_EMBEDDING_3_SMALL_CONFIG.model_copy(update=dict(id=bge, owned_by="ellm"))
            ),
            # Create deployments
            create_deployment(ELLM_DESCRIBE_DEPLOYMENT),
            create_deployment(TEXT_EMBEDDING_3_SMALL_DEPLOYMENT),
            create_deployment(RERANK_ENGLISH_v3_SMALL_DEPLOYMENT),
            create_deployment(
                TEXT_EMBEDDING_3_SMALL_DEPLOYMENT.model_copy(update=dict(model_id=bge))
            ),
        ):
            client = JamAI(user_id=superuser.id, project_id=p0.id)
            image_uri = upload_file(client, FILES["rabbit.jpeg"]).uri
            audio_uri = upload_file(client, FILES["gutter.mp3"]).uri
            document_uri = upload_file(
                client, FILES["LLMs as Optimizers [DeepMind ; 2023].pdf"]
            ).uri
            yield ServingContext(
                superuser_id=superuser.id,
                superorg_id=superorg.id,
                project_id=p0.id,
                embedding_size=embed_config.final_embedding_size,
                image_uri=image_uri,
                audio_uri=audio_uri,
                document_uri=document_uri,
                chat_model_id=desc_llm_config.id,
                embed_model_id=embed_config.id,
                rerank_model_id=rerank_config.id,
            )


def test_get_list_templates(setup: ServingContext):
    super_client = JamAI(user_id=setup.superuser_id)
    public_client = JamAI()
    # List projects
    response = super_client.projects.list_projects(organization_id=setup.superorg_id)
    assert isinstance(response, Page)
    assert len(response.items) == 1
    assert response.total == 1
    # List templates
    response = super_client.templates.list_templates()
    assert isinstance(response, Page)
    assert len(response.items) == 0
    assert response.total == 0
    assert public_client.templates.list_templates().total == 0
    # Create templates
    templates = []
    try:
        templates = [_create_template(super_client) for _ in range(2)]
        # There are now two templates
        response = super_client.templates.list_templates()
        assert len(response.items) == 2
        assert response.total == 2
        assert all(t.name.startswith("Template") for t in templates)
        assert public_client.templates.list_templates().total == 2
        # There is still just one project
        assert super_client.projects.list_projects(organization_id=setup.superorg_id).total == 1
        # Get a template
        template = super_client.templates.get_template(templates[0].id)
        assert template.id == templates[0].id
        assert template.name == templates[0].name
    finally:
        for template in templates:
            super_client.projects.delete_project(template.id)


def test_get_list_template_tables_rows(setup: ServingContext):
    # Create template
    template = _create_template(JamAI(user_id=setup.superuser_id))
    super_client = JamAI(user_id=setup.superuser_id, project_id=template.id)
    public_client = JamAI()
    tables: list[TableMetaResponse] = []
    try:
        # Create the tables
        for table_type in TableType:
            if table_type == TableType.CHAT:
                parquet_filepath = FILES["export-v0.4-chat-agent.parquet"]
            else:
                parquet_filepath = FILES[f"export-v0.4-{table_type}.parquet"]
            table = super_client.table.import_table(
                table_type,
                TableImportRequest(file_path=parquet_filepath, table_id_dst=None),
            )
            assert isinstance(table, TableMetaResponse)
            tables.append(table)
        # Get and list tables
        # Get and list table rows
        for i, table_type in enumerate(TableType):
            table_id = tables[i].id
            # List tables
            response = super_client.templates.list_tables(template.id, table_type)
            assert isinstance(response, Page)
            assert all(isinstance(r, TableMetaResponse) for r in response.items)
            assert len(response.items) == 1
            assert response.total == 1
            assert public_client.templates.list_tables(template.id, table_type).total == 1
            # Get table
            table = super_client.templates.get_table(template.id, table_type, table_id)
            assert isinstance(table, TableMetaResponse)
            assert table.id == response.items[0].id
            table = public_client.templates.get_table(template.id, table_type, table_id)
            assert table.id == response.items[0].id
            # List rows
            rows = super_client.templates.list_table_rows(template.id, table_type, table_id)
            assert isinstance(rows, Page)
            assert all(isinstance(r, dict) for r in rows.items)
            assert len(rows.items) == 1
            assert rows.total == 1
            rows = public_client.templates.list_table_rows(template.id, table_type, table_id)
            assert rows.total == 1
            # Get row
            row = super_client.templates.get_table_row(
                template.id, table_type, table_id, rows.items[0]["ID"]
            )
            assert isinstance(row, dict)
            assert row["ID"] == rows.items[0]["ID"]
            row = public_client.templates.get_table_row(
                template.id, table_type, table_id, rows.items[0]["ID"]
            )
            assert row["ID"] == rows.items[0]["ID"]
            # Try generation
            if table_type == TableType.ACTION:
                response = add_table_rows(
                    super_client, table_type, table_id, [{"question": "Why"}], stream=False
                )
                assert len(response.rows) == 1
                assert "There is a text" in response.rows[0].columns["answer"].content
            elif table_type == TableType.KNOWLEDGE:
                response = add_table_rows(super_client, table_type, table_id, [{}], stream=False)
                assert len(response.rows) == 1
            else:
                response = add_table_rows(
                    super_client, table_type, table_id, [{"User": "Hi"}], stream=False
                )
                assert len(response.rows) == 1
                assert "There is a text" in response.rows[0].columns["AI"].content
            # List rows again
            rows = super_client.templates.list_table_rows(template.id, table_type, table_id)
            assert isinstance(rows, Page)
            assert all(isinstance(r, dict) for r in rows.items)
            assert len(rows.items) == 2
            assert rows.total == 2
            rows = public_client.templates.list_table_rows(template.id, table_type, table_id)
            assert rows.total == 2
    finally:
        for table in tables:
            super_client.table.delete_table(table_type, table.id)
