import re
from dataclasses import dataclass
from os.path import dirname, join, realpath
from tempfile import TemporaryDirectory

import httpx
import pytest

from jamaibase import JamAI
from jamaibase.types import (
    GetURLResponse,
    LLMGenConfig,
    OrganizationCreate,
    OrgMemberRead,
    Page,
    ProjectCreate,
    ProjectMemberRead,
    ProjectRead,
    ProjectUpdate,
    RAGParams,
    TableImportRequest,
)
from jamaibase.utils.exceptions import (
    AuthorizationError,
    BadInputError,
    ForbiddenError,
    ResourceExistsError,
    ResourceNotFoundError,
)
from owl.db import TEMPLATE_ORG_ID
from owl.types import GEN_CONFIG_VAR_PATTERN, ColumnDtype, Role, TableType
from owl.utils.test import (
    ELLM_DESCRIBE_CONFIG,
    ELLM_DESCRIBE_DEPLOYMENT,
    TEXT_EMBEDDING_3_SMALL_CONFIG,
    TEXT_EMBEDDING_3_SMALL_DEPLOYMENT,
    RERANK_ENGLISH_v3_SMALL_CONFIG,
    RERANK_ENGLISH_v3_SMALL_DEPLOYMENT,
    create_deployment,
    create_model_config,
    create_organization,
    create_project,
    create_user,
    get_file_map,
    list_table_rows,
    setup_organizations,
    setup_projects,
    upload_file,
)

TEST_FILE_DIR = join(dirname(dirname(realpath(__file__))), "files")
FILES = get_file_map(TEST_FILE_DIR)

FILE_COLUMNS = ["image", "audio", "document"]


def test_create_project():
    """
    - Project creation
    - User cannot be deleted if they are still an owner
    """
    with (
        create_user() as superuser,
        create_user(dict(email="russell@up.com", name="User")) as user,
    ):
        assert superuser.id == "0"
        assert user.id != "0"
        client = JamAI(user_id=user.id)
        with (
            create_organization(
                OrganizationCreate(name="System"), user_id=superuser.id
            ) as superorg,
            create_organization(OrganizationCreate(name="Clubhouse"), user_id=user.id) as org,
        ):
            assert superorg.id == "0"
            assert org.id != "0"
            # Standard creation
            with (
                create_project(user_id=superuser.id),
                create_project(dict(name="Mickey 17"), user_id=user.id, organization_id=org.id),
            ):
                with pytest.raises(BadInputError, match="projects with the user as owner"):
                    client.users.delete_user()
            with pytest.raises(BadInputError, match="organizations with the user as owner"):
                client.users.delete_user()


@pytest.mark.cloud
def test_create_project_auth():
    from owl.db import sync_session
    from owl.db.models.cloud import APIKey

    with (
        setup_organizations() as ctx,
        create_project(user_id=ctx.user.id, organization_id=ctx.org.id) as p0,
    ):
        ### --- Test Project Key auth --- ###
        # Project-linked PAT
        pat = JamAI(user_id=ctx.user.id).users.create_pat(dict(name="pat", project_id=p0.id))
        assert pat.id.startswith("jamai_pat_")
        client = JamAI(user_id=ctx.user.id, token=pat.id)
        name = "Mickey 18"
        p1 = client.projects.create_project(dict(name=name, organization_id=ctx.org.id))
        assert p1.name == name
        with pytest.raises(AuthorizationError, match="invalid authorization token"):
            JamAI(user_id=ctx.user.id, token=f"{pat.id}xx").projects.create_project(
                dict(name=name, organization_id=ctx.org.id)
            )
        # No project link
        pat = JamAI(user_id=ctx.user.id).users.create_pat(dict(name="pat", project_id=None))
        assert pat.id.startswith("jamai_pat_")
        client = JamAI(user_id=ctx.user.id, token=pat.id)
        name = "Mickey 19"
        p1 = client.projects.create_project(dict(name=name, organization_id=ctx.org.id))
        assert p1.name == name
        with pytest.raises(AuthorizationError, match="invalid authorization token"):
            JamAI(user_id=ctx.user.id, token=f"{pat.id}xx").projects.create_project(
                dict(name=name, organization_id=ctx.org.id)
            )

        ### --- Test Legacy Organization Key auth --- ###
        with sync_session() as session:
            key = APIKey(id="jamai_sk_legacy", organization_id=ctx.org.id)
            session.add(key)
            session.commit()
            session.refresh(key)
        client = JamAI(user_id=ctx.user.id, token=key.id)
        name = "Mickey 20"
        p1 = client.projects.create_project(dict(name=name, organization_id=ctx.org.id))
        assert p1.name == name
        with pytest.raises(AuthorizationError, match="invalid authorization token"):
            JamAI(user_id=ctx.user.id, token=f"{key.id}xx").projects.create_project(
                dict(name=name, organization_id=ctx.org.id)
            )

        # List projects
        projects = client.projects.list_projects(ctx.org.id)
        assert isinstance(projects, Page)
        assert len(projects.items) == 4
        assert projects.total == 4


@pytest.mark.cloud
def test_create_project_permission():
    with setup_organizations() as ctx:
        assert ctx.user.id != "0"
        with pytest.raises(ForbiddenError):
            with create_project(
                dict(name="My First Project", organization_id=ctx.superorg.id),
                user_id=ctx.user.id,
            ):
                pass


# def test_create_existing_project():
#     with setup_organizations() as ctx:
#         with create_project(user_id=ctx.superuser.id) as project:
#             with pytest.raises(ResourceExistsError):
#                 with create_project(
#                     dict(id=project.id, name="Mickey 1"), user_id=ctx.superuser.id
#                 ):
#                     pass


def test_create_project_duplicate_name():
    with setup_organizations() as ctx, create_project(user_id=ctx.superuser.id) as p0:
        with (
            create_project(dict(name=p0.name), user_id=ctx.superuser.id) as p1,
            create_project(dict(name=p0.name), user_id=ctx.superuser.id) as p2,
        ):
            assert isinstance(p1, ProjectRead)
            assert p1.name == f"{p0.name} (1)"
            assert isinstance(p2, ProjectRead)
            assert p2.name == f"{p0.name} (2)"
            assert len({p0.id, p1.id, p2.id}) == 3


def test_create_project_missing_org():
    with setup_organizations() as ctx:
        with pytest.raises((ForbiddenError, ResourceNotFoundError)):
            with create_project(
                dict(name="My First Project"),
                user_id=ctx.superuser.id,
                organization_id="nonexistent",
            ):
                pass


def test_list_projects():
    with setup_organizations() as ctx:
        with (
            create_project(user_id=ctx.superuser.id),
            create_project(dict(name="Mickey 1"), user_id=ctx.superuser.id),
        ):
            projects = JamAI(user_id=ctx.superuser.id).projects.list_projects(ctx.superorg.id)
            assert isinstance(projects, Page)
            assert len(projects.items) == 2


@pytest.mark.cloud
def test_list_projects_permission():
    """
    Test project list permission.
    - ADMIN and MEMBER can list all projects.
    - Non-members cannot list projects at all.
    - GUEST can only list projects that they are a member of.
    """
    with (
        setup_organizations() as ctx,
        create_project(user_id=ctx.superuser.id),
        create_project(user_id=ctx.superuser.id) as p1,
        create_project(user_id=ctx.user.id, organization_id=ctx.org.id),
    ):
        super_client = JamAI(user_id=ctx.superuser.id)
        client = JamAI(user_id=ctx.user.id)
        ### --- Admin can list all projects --- ###
        projects = super_client.projects.list_projects(ctx.superorg.id)
        assert isinstance(projects, Page)
        assert len(projects.items) == 2
        ### --- Non-member fail --- ###
        with pytest.raises(ForbiddenError):
            client.projects.list_projects(ctx.superorg.id)
        ### --- Guest can list projects that they are a member of --- ###
        # Join organization as guest and project
        membership = super_client.organizations.join_organization(
            ctx.user.id,
            organization_id=ctx.superorg.id,
            role=Role.GUEST,
        )
        assert isinstance(membership, OrgMemberRead)
        membership = super_client.projects.join_project(
            ctx.user.id,
            project_id=p1.id,
            role=Role.MEMBER,
        )
        assert isinstance(membership, ProjectMemberRead)
        projects = client.projects.list_projects(ctx.superorg.id)
        assert isinstance(projects, Page)
        assert len(projects.items) == 1
        # Project role doesn't matter
        membership = super_client.projects.update_member_role(
            user_id=ctx.user.id,
            project_id=p1.id,
            role=Role.GUEST,
        )
        assert isinstance(membership, ProjectMemberRead)
        assert membership.role == Role.GUEST
        projects = client.projects.list_projects(ctx.superorg.id)
        assert isinstance(projects, Page)
        assert len(projects.items) == 1
        ### --- Member can list all projects --- ###
        # Update org role to MEMBER
        membership = super_client.organizations.update_member_role(
            user_id=ctx.user.id,
            organization_id=ctx.superorg.id,
            role=Role.MEMBER,
        )
        assert isinstance(membership, OrgMemberRead)
        assert membership.role == Role.MEMBER
        projects = client.projects.list_projects(ctx.superorg.id)
        assert isinstance(projects, Page)
        assert len(projects.items) == 2


@pytest.mark.cloud
def test_update_project_permission():
    with (
        setup_organizations() as ctx,
        create_project(user_id=ctx.user.id, organization_id=ctx.org.id) as project,
    ):
        client = JamAI(user_id=ctx.user.id)
        # Join organization and project as member
        membership = client.organizations.join_organization(
            ctx.superuser.id,
            organization_id=ctx.org.id,
            role=Role.MEMBER,
        )
        assert isinstance(membership, OrgMemberRead)
        membership = client.projects.join_project(
            ctx.superuser.id,
            project_id=project.id,
            role=Role.MEMBER,
        )
        assert isinstance(membership, ProjectMemberRead)
        # Admin OK
        updated_proj = client.projects.update_project(project.id, ProjectUpdate(name="New Name"))
        assert isinstance(updated_proj, ProjectRead)
        # Member fail
        with pytest.raises(ForbiddenError):
            JamAI(user_id=ctx.superuser.id).projects.update_project(
                project.id, ProjectUpdate(name="Another Name")
            )


@pytest.mark.cloud
def test_project_deletion_removes_from_secret_allowed_projects():
    """Test that when a project is deleted, it's removed from secret allowed_projects lists."""
    from owl.types import SecretCreate

    with (
        setup_organizations() as ctx,
        create_project(
            dict(name="Secret Test Project 1"), user_id=ctx.user.id, organization_id=ctx.org.id
        ) as project1,
        create_project(
            dict(name="Secret Test Project 2"), user_id=ctx.user.id, organization_id=ctx.org.id
        ) as project2,
    ):
        client = JamAI(user_id=ctx.user.id)
        secret = client.secrets.create_secret(
            body=SecretCreate(
                name="TEST_PROJECT_ACCESS_SECRET",
                value="test-value",
                allowed_projects=[project1.id, project2.id],
            ),
            organization_id=ctx.org.id,
        )

        try:
            fetched = client.secrets.get_secret(organization_id=ctx.org.id, name=secret.name)
            assert set(fetched.allowed_projects) == set([project1.id, project2.id])

            # Delete project1
            client.projects.delete_project(project1.id)
            fetched_after = client.secrets.get_secret(organization_id=ctx.org.id, name=secret.name)
            assert set(fetched_after.allowed_projects) == set([project2.id])
            assert project1.id not in fetched_after.allowed_projects

            # Delete project2
            client.projects.delete_project(project2.id)
            fetched_final = client.secrets.get_secret(organization_id=ctx.org.id, name=secret.name)
            assert fetched_final.allowed_projects == []

        finally:
            client.secrets.delete_secret(
                organization_id=ctx.org.id, name=secret.name, missing_ok=True
            )


def test_update_project_owner():
    with (
        setup_projects() as ctx,
        create_user(dict(email="ClaudiaT@up.com", name="Claudia Tiedemann")) as org_admin,
    ):
        first_owner_client = JamAI(user_id=ctx.user.id)
        org_admin_client = JamAI(user_id=org_admin.id)

        # Should fail because project does not exist
        with pytest.raises(ResourceNotFoundError, match="is not found."):
            first_owner_client.projects.update_owner(
                new_owner_id="fake", project_id=ctx.projects[1].id
            )

        # Should fail because new owner is not a current member of the project
        with pytest.raises(ForbiddenError, match="The new owner is not a member of this project"):
            first_owner_client.projects.update_owner(
                new_owner_id=org_admin.id, project_id=ctx.projects[1].id
            )

        # Should fail because the User sending the request is not the owner.
        membership = first_owner_client.organizations.join_organization(
            org_admin.id, organization_id=ctx.org.id, role=Role.ADMIN
        )
        assert isinstance(membership, OrgMemberRead)
        membership = first_owner_client.projects.join_project(
            org_admin.id, project_id=ctx.projects[1].id, role=Role.ADMIN
        )
        assert isinstance(membership, ProjectMemberRead)

        with pytest.raises(
            ForbiddenError, match="Only the owner can transfer the ownership of a project."
        ):
            org_admin_client.projects.update_owner(
                new_owner_id=org_admin.id, project_id=ctx.projects[1].id
            )

        # Should return the same org since the new owner id is the same as the current one
        first_owner_client.projects.update_owner(
            new_owner_id=ctx.user.id, project_id=ctx.projects[1].id
        )

        # Should succeed since the new owner is now a member of the project
        new_proj = first_owner_client.projects.update_owner(
            new_owner_id=org_admin.id, project_id=ctx.projects[1].id
        )
        assert new_proj.model_dump(exclude=["owner", "updated_at"]) == ctx.projects[1].model_dump(
            exclude=["owner", "updated_at"]
        )
        assert new_proj.owner != ctx.projects[1].owner
        assert new_proj.updated_at != ctx.projects[1].updated_at
        assert new_proj.owner == org_admin.id

        # Should fail because this user is no longer the owner
        with pytest.raises(
            ForbiddenError, match="Only the owner can transfer the ownership of a project."
        ):
            first_owner_client.projects.update_owner(
                new_owner_id=org_admin.id, project_id=ctx.projects[1].id
            )
        # New owner will be ADMIN
        membership = org_admin_client.projects.get_member(
            user_id=org_admin.id, project_id=ctx.projects[1].id
        )
        assert isinstance(membership, ProjectMemberRead)
        assert membership.role == Role.ADMIN

        # Should fail because this is the last membership for this user and he is the current owner of the project
        with pytest.raises(ForbiddenError, match="Owner cannot leave the project."):
            org_admin_client.projects.leave_project(org_admin.id, ctx.projects[1].id)

        # Return the project to the first owner
        org_admin_client.projects.update_owner(
            new_owner_id=ctx.user.id, project_id=ctx.projects[1].id
        )

        # Should succeed after returning the project to the old owner.
        org_admin_client.projects.leave_project(org_admin.id, ctx.projects[1].id)


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
        create_user() as superuser,
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


def _check_tables(user_id: str, project_id: str):
    client = JamAI(user_id=user_id, project_id=project_id)
    for table_type in TableType:
        tables = client.table.list_tables(table_type, parent_id="_agent_")
        assert tables.total == 1
        rows = list_table_rows(client, table_type, tables.items[0].id)
        assert rows.total == 1
        if table_type == TableType.ACTION:
            # Check image content
            urls = client.file.get_raw_urls([rows.values[0]["image"]])
            assert isinstance(urls, GetURLResponse)
            image = httpx.get(urls.urls[0]).content
            with open(FILES["cifar10-deer.jpg"], "rb") as f:
                assert image == f.read()


def test_project_import_export(
    setup: ServingContext,
):
    """
    Test project import and export.

    Args:
        setup (ServingContext): Setup.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    tables = []
    try:
        # Create the tables
        for table_type in TableType:
            if table_type == TableType.CHAT:
                parquet_filepath = FILES["export-v0.4-chat-agent.parquet"]
            else:
                parquet_filepath = FILES[f"export-v0.4-{table_type}.parquet"]
            table = client.table.import_table(
                table_type,
                TableImportRequest(file_path=parquet_filepath, table_id_dst=None),
            )
            tables.append(table)
        # Export
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, f"{setup.project_id}.parquet")
            with open(file_path, "wb") as f:
                f.write(client.projects.export_project(setup.project_id))
            # Import as new project
            imported_project = client.projects.import_project(
                file_path,
                project_id="",
                organization_id=setup.superorg_id,
            )
            assert isinstance(imported_project, ProjectRead)
            assert imported_project.id != setup.project_id
            _check_tables(setup.superuser_id, imported_project.id)
            # Import into existing project
            with create_project(
                dict(name="Superorg Project 1"),
                user_id=setup.superuser_id,
                organization_id=setup.superorg_id,
            ) as p1:
                imported_project = client.projects.import_project(
                    file_path,
                    project_id=p1.id,
                    organization_id="",
                )
                assert isinstance(imported_project, ProjectRead)
                assert imported_project.id == p1.id
                _check_tables(setup.superuser_id, imported_project.id)
                # Should not change existing metadata
                project = client.projects.get_project(p1.id)
                assert project.name == "Superorg Project 1"
                # Should fail if tables already exist
                with pytest.raises(ResourceExistsError):
                    client.projects.import_project(
                        file_path,
                        project_id=p1.id,
                        organization_id="",
                    )
    finally:
        for table in tables:
            client.table.delete_table(table_type, table.id)


@pytest.mark.parametrize("version", ["v0.4"])
def test_project_import_parquet(
    setup: ServingContext,
    version: str,
):
    """
    Test project import from an existing Parquet file.
    - Import as new project from v0.4 file
    - Import into existing parquet from v0.4 file
    - Import v0.4 file with table and column names that are too long (test truncation)

    Args:
        setup (ServingContext): Setup.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    ### --- Import as new project --- ###
    imported_project = client.projects.import_project(
        FILES[f"export-{version}-project.parquet"],
        project_id="",
        organization_id=setup.superorg_id,
    )
    assert imported_project.id != setup.project_id
    assert imported_project.name == "Test Project 新しい"
    _check_tables(setup.superuser_id, imported_project.id)
    ### --- Import into existing project --- ###
    with create_project(
        dict(name="Superorg Project 2"),
        user_id=setup.superuser_id,
        organization_id=setup.superorg_id,
    ) as p1:
        imported_project = client.projects.import_project(
            FILES[f"export-{version}-project.parquet"],
            project_id=p1.id,
            organization_id="",
        )
        assert imported_project.id == p1.id
        assert imported_project.name == p1.name
        assert imported_project.name != "Test Project 新しい"
        _check_tables(setup.superuser_id, imported_project.id)
    ### --- Import table and column names that are too long --- ###
    imported_project = client.projects.import_project(
        FILES[f"export-{version}-project-long-name.parquet"],
        project_id="",
        organization_id=setup.superorg_id,
    )
    assert imported_project.id != setup.project_id
    client = JamAI(user_id=setup.superuser_id, project_id=imported_project.id)
    # Check tables
    tables = client.table.list_tables(TableType.KNOWLEDGE)
    assert len(tables.items) == 1
    assert tables.total == 1
    kt = tables.items[0]
    assert len(kt.id) == 100
    tables = client.table.list_tables(TableType.ACTION)
    assert len(tables.items) == 1
    assert tables.total == 1
    at = tables.items[0]
    assert len(at.id) == 100
    assert len(at.cols) == 4
    for col in at.cols[2:]:
        assert len(col.id) == 100
    assert at.cols[2].dtype == ColumnDtype.IMAGE
    assert at.cols[3].dtype == ColumnDtype.STR
    cfg = at.cols[3].gen_config
    assert isinstance(cfg, LLMGenConfig)
    ref_ids = re.findall(GEN_CONFIG_VAR_PATTERN, cfg.prompt)
    assert len(ref_ids) == 1
    assert ref_ids[0] == at.cols[2].id
    assert isinstance(cfg.rag_params, RAGParams)
    assert cfg.rag_params.table_id == kt.id
    tables = client.table.list_tables(TableType.CHAT)
    assert len(tables.items) == 2
    assert tables.total == 2
    tables = client.table.list_tables(TableType.CHAT, parent_id="_agent_")
    assert len(tables.items) == 1
    assert tables.total == 1
    agent = tables.items[0]
    assert len(agent.id) == 100
    tables = client.table.list_tables(TableType.CHAT, parent_id="_chat_")
    assert len(tables.items) == 1
    assert tables.total == 1
    ct = tables.items[0]
    assert len(ct.id) == 100
    assert agent.parent_id is None
    assert ct.parent_id == agent.id


def test_template_import_export(
    setup: ServingContext,
):
    """
    Test template import.

    Args:
        setup (ServingContext): Setup.
    """
    # Create template
    template = JamAI(user_id=setup.superuser_id).projects.create_project(
        ProjectCreate(organization_id=TEMPLATE_ORG_ID, name="Template")
    )
    client = JamAI(user_id=setup.superuser_id, project_id=template.id)
    tables = []
    try:
        # Create the tables
        for table_type in TableType:
            if table_type == TableType.CHAT:
                parquet_filepath = FILES["export-v0.4-chat-agent.parquet"]
            else:
                parquet_filepath = FILES[f"export-v0.4-{table_type}.parquet"]
            table = client.table.import_table(
                table_type,
                TableImportRequest(file_path=parquet_filepath, table_id_dst=None),
            )
            tables.append(table)
        # Import as new project
        imported_project = client.projects.import_template(
            template.id,
            project_id="",
            organization_id=setup.superorg_id,
        )
        assert isinstance(imported_project, ProjectRead)
        assert imported_project.id != setup.project_id
        _check_tables(setup.superuser_id, imported_project.id)
        # Import into existing project
        with create_project(
            dict(name="Superorg Project 2"),
            user_id=setup.superuser_id,
            organization_id=setup.superorg_id,
        ) as p1:
            imported_project = client.projects.import_template(
                template.id,
                project_id=p1.id,
                organization_id="",
            )
            assert isinstance(imported_project, ProjectRead)
            assert imported_project.id == p1.id
            _check_tables(setup.superuser_id, imported_project.id)
            # Should not change existing metadata
            project = client.projects.get_project(p1.id)
            assert project.name == "Superorg Project 2"
            # Should fail if tables already exist
            with pytest.raises(ResourceExistsError):
                client.projects.import_template(
                    template.id,
                    project_id=p1.id,
                    organization_id="",
                )
    finally:
        for table in tables:
            client.table.delete_table(table_type, table.id)


if __name__ == "__main__":
    test_list_projects()
