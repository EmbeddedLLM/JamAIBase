import random
from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from jamaibase import JamAI
from jamaibase.types import OkResponse
from owl.db import sync_session
from owl.db.models.oss import Organization, OrgMember, Secret
from owl.types import (
    OrganizationCreate,
    Role,
    SecretCreate,
    SecretUpdate,
)
from owl.utils.crypt import generate_key
from owl.utils.exceptions import (
    BadInputError,
    ForbiddenError,
    ResourceExistsError,
    ResourceNotFoundError,
)
from owl.utils.test import create_organization, create_project, create_user, setup_organizations


@dataclass(slots=True)
class OrgContext:
    superuser: object
    user: object
    member: object
    superorg: object
    org: object


@dataclass(slots=True)
class MultiOrgContext:
    superuser: object
    user_a: object
    user_b: object
    superorg: object
    org_a: object
    org_b: object


@pytest.fixture(scope="module")
def org_context():
    """Fixture to set up organizations and users."""
    with setup_organizations() as ctx:
        # Create a non-admin member in the regular organization
        with create_user(
            dict(email=f"member-{generate_key(8)}@test.com", name="Non-Admin Member")
        ) as member_user:
            with sync_session() as session:
                org_member = OrgMember(
                    user_id=member_user.id, organization_id=ctx.org.id, role=Role.MEMBER
                )
                session.add(org_member)
                session.commit()

            yield OrgContext(
                superuser=ctx.superuser,
                user=ctx.user,
                member=member_user,
                superorg=ctx.superorg,
                org=ctx.org,
            )


@pytest.fixture(scope="module")
def admin_client(org_context):
    """Fixture for admin client."""
    return JamAI(user_id=org_context.superuser.id)


@pytest.fixture(scope="module")
def non_admin_client(org_context):
    """Fixture for non-admin client (MEMBER role, not ADMIN)."""
    return JamAI(user_id=org_context.member.id)


@pytest.fixture(scope="module")
def multi_org_context():
    """Fixture to set up multiple regular organizations for testing org isolation."""

    # Create system admin
    with create_user(
        dict(email=f"superuser-{generate_key(8)}@test.com", name="System Admin")
    ) as superuser:
        # Create two regular users in different organizations
        with (
            create_user(
                dict(email=f"org-a-admin-{generate_key(8)}@test.com", name="Org A Admin")
            ) as user_a,
            create_user(
                dict(email=f"org-b-admin-{generate_key(8)}@test.com", name="Org B Admin")
            ) as user_b,
        ):
            # Create system org and two regular orgs
            with (
                create_organization(
                    OrganizationCreate(name="System"), user_id=superuser.id
                ) as superorg,
                create_organization(
                    OrganizationCreate(name="Organization A"), user_id=user_a.id
                ) as org_a,
                create_organization(
                    OrganizationCreate(name="Organization B"), user_id=user_b.id
                ) as org_b,
            ):
                yield MultiOrgContext(
                    superuser=superuser,
                    user_a=user_a,
                    user_b=user_b,
                    superorg=superorg,
                    org_a=org_a,
                    org_b=org_b,
                )


def test_secret_lifecycle(admin_client, org_context):
    org_id = org_context.superorg.id
    secret_name = "SECRET_LIFECYCLE"
    secret_value = "!@#$%^qwertyasdfg"
    second_secret_name = "SECOND_SECRET"

    with (
        create_project(
            dict(name="project1"), user_id=org_context.superuser.id, organization_id=org_id
        ) as proj1,
        create_project(
            dict(name="project2"), user_id=org_context.superuser.id, organization_id=org_id
        ) as proj2,
    ):
        try:
            # creates secret
            secret = admin_client.secrets.create_secret(
                body=SecretCreate(name=secret_name, value=secret_value, allowed_projects=None),
                organization_id=org_id,
            )

            assert secret.name == secret_name
            assert secret.value == secret_value
            assert secret.allowed_projects is None

            # fetches secret
            fetched_secret = admin_client.secrets.get_secret(
                organization_id=org_id, name=secret_name
            )
            assert fetched_secret.name == secret_name
            assert fetched_secret.value == "***"  # masked on get
            assert fetched_secret.allowed_projects is None

            # updates value
            secret_value_2 = f"{secret_value}_2"
            updated_secret_value = admin_client.secrets.update_secret(
                organization_id=org_id, name=secret_name, body=SecretUpdate(value=secret_value_2)
            )
            assert updated_secret_value.value == secret_value_2
            assert updated_secret_value.allowed_projects is None  # unchanged

            # updates allowed_projects
            updated_secret_project_access = admin_client.secrets.update_secret(
                organization_id=org_id,
                name=secret_name,
                body=SecretUpdate(allowed_projects=[proj1.id, proj2.id]),
            )
            assert set(updated_secret_project_access.allowed_projects) == set([proj1.id, proj2.id])

            updated_secret_project_access_empty = admin_client.secrets.update_secret(
                organization_id=org_id,
                name=secret_name,
                body=SecretUpdate(allowed_projects=[]),
            )
            assert updated_secret_project_access_empty.allowed_projects == []

            # duplicated creation failure
            with pytest.raises(ResourceExistsError):
                admin_client.secrets.create_secret(
                    body=SecretCreate(name=secret_name, value=secret_value, allowed_projects=None),
                    organization_id=org_id,
                )

            # creates and list secrets
            admin_client.secrets.create_secret(
                body=SecretCreate(name=second_secret_name, value="value2", allowed_projects=None),
                organization_id=org_id,
            )
            test_list_secrets = admin_client.secrets.list_secrets(organization_id=org_id)
            assert len(test_list_secrets.items) == 2
            secret_names = {s.name for s in test_list_secrets.items}
            assert secret_names == {secret_name, second_secret_name}
            for s in test_list_secrets.items:
                assert s.value == "***"  # masked

            # deletes secret
            delete_response = admin_client.secrets.delete_secret(
                organization_id=org_id, name=secret_name, missing_ok=True
            )
            assert isinstance(delete_response, OkResponse)

            with pytest.raises(ResourceNotFoundError):
                admin_client.secrets.get_secret(organization_id=org_id, name=secret_name)

            with pytest.raises(ResourceNotFoundError):
                admin_client.secrets.update_secret(
                    organization_id=org_id, name=secret_name, body=SecretUpdate(value="x")
                )

            with pytest.raises(ResourceNotFoundError):
                admin_client.secrets.delete_secret(
                    organization_id=org_id, name=secret_name, missing_ok=False
                )

        finally:
            admin_client.secrets.delete_secret(
                organization_id=org_id, name=secret_name, missing_ok=True
            )
            admin_client.secrets.delete_secret(
                organization_id=org_id, name=second_secret_name, missing_ok=True
            )


@pytest.mark.parametrize(
    "name, expected_stored_name",
    [
        ("valid_name", "VALID_NAME"),
        ("VALID123", "VALID123"),
        ("mixed_CASE_Secret", "MIXED_CASE_SECRET"),
        ("_123_SECRET", "_123_SECRET"),
        ("___", "___"),
    ],
)
def test_secret_name_valid(admin_client, org_context, name, expected_stored_name):
    """Test various valid name formats and case-insensitive operations."""
    secret = admin_client.secrets.create_secret(
        body=SecretCreate(name=name, value="value", allowed_projects=None),
        organization_id=org_context.superorg.id,
    )

    try:
        assert secret.name == expected_stored_name

        fetched_secret = admin_client.secrets.get_secret(
            organization_id=org_context.superorg.id, name=name.lower()
        )
        assert fetched_secret.name == expected_stored_name
        assert fetched_secret.value == "***"  # masked

        updated_secret = admin_client.secrets.update_secret(
            organization_id=org_context.superorg.id,
            name=name,
            body=SecretUpdate(value="value2"),
        )
        assert updated_secret.name == expected_stored_name
        assert updated_secret.value == "value2"

        response = admin_client.secrets.delete_secret(
            organization_id=org_context.superorg.id, name=name
        )
        assert isinstance(response, OkResponse)
        with pytest.raises(ResourceNotFoundError):
            admin_client.secrets.get_secret(
                organization_id=org_context.superorg.id, name=secret.name
            )
    finally:
        admin_client.secrets.delete_secret(
            organization_id=org_context.superorg.id, name=expected_stored_name, missing_ok=True
        )


@pytest.mark.parametrize(
    "invalid_name",
    [
        "1INVALID",  # starts with number
        "has spaces",  # spaces
        "bad-char",  # dash
        "bad.char",  # dot
        "",  # empty
    ],
)
def test_secret_name_invalid(admin_client, org_context, invalid_name):
    match = (
        "String should have at least 1 character"
        if invalid_name == ""
        else "String should match pattern"
    )
    with pytest.raises(ValidationError, match=match):
        admin_client.secrets.create_secret(
            body=SecretCreate(name=invalid_name, value="value", allowed_projects=None),
            organization_id=org_context.superorg.id,
        )


name_value_pairs = [
    ("whitespace", "   "),
    ("mixed_whitespace", "\t\n "),
    ("very_long", "A" * 5000),
    ("special_chars", "!@#$%^&*()"),
    ("unicode", "Hello 世界 🌍"),
    ("emojis_only", "🔐🔑🗝️💎"),
    ("json", '{"key": "value"}'),
    ("sql_injection", "'; DROP TABLE secrets; --"),
    ("null_bytes", "val\x00ue"),
]
randoms = list(range(len(name_value_pairs)))
random.shuffle(randoms)
secret_name_value_pairs = [
    (name_value_pairs[i1][0], name_value_pairs[i1][1], name_value_pairs[i2][1])
    for i1, i2 in zip(list(range(len(name_value_pairs))), randoms, strict=True)
]


@pytest.mark.parametrize("name, value, updated_value", secret_name_value_pairs)
def test_secret_value_handling(admin_client, org_context, name, value, updated_value):
    try:
        secret = admin_client.secrets.create_secret(
            body=SecretCreate(name=name, value=value),
            organization_id=org_context.superorg.id,
        )
        assert secret.value == value

        # fetch and verify masked value
        fetched_secret = admin_client.secrets.get_secret(
            organization_id=org_context.superorg.id, name=name
        )
        assert fetched_secret.value == "***"

        # updates to same value
        updated_secret_same = admin_client.secrets.update_secret(
            organization_id=org_context.superorg.id, name=name, body=SecretUpdate(value=value)
        )
        assert updated_secret_same.value == value

        # updates to different value
        updated_secret = admin_client.secrets.update_secret(
            organization_id=org_context.superorg.id,
            name=name,
            body=SecretUpdate(value=updated_value),
        )
        assert updated_secret.value == updated_value
    finally:
        admin_client.secrets.delete_secret(
            organization_id=org_context.superorg.id, name=name, missing_ok=True
        )


@pytest.mark.cloud
def test_member_role_permissions(non_admin_client, org_context):
    """Test that non-admin users (MEMBER role) can get/list, but cannot create/update/delete secrets."""
    admin_client_ = JamAI(user_id=org_context.user.id)
    org_id = org_context.org.id
    secret = admin_client_.secrets.create_secret(
        body=SecretCreate(name="MEMBER_TEST_SECRET", value="test-value"), organization_id=org_id
    )

    try:
        # MEMBER can get the secret
        fetched = non_admin_client.secrets.get_secret(organization_id=org_id, name=secret.name)
        assert fetched.name == secret.name
        assert fetched.value == "***"  # masked

        # MEMBER can list secrets
        secrets = non_admin_client.secrets.list_secrets(organization_id=org_id)
        assert any(s.name == secret.name for s in secrets.items)

        # MEMBER cannot create secrets
        with pytest.raises(ForbiddenError):
            non_admin_client.secrets.create_secret(
                body=SecretCreate(name="NEW_SECRET", value="value"), organization_id=org_id
            )

        # MEMBER cannot update secrets
        with pytest.raises(ForbiddenError):
            non_admin_client.secrets.update_secret(
                organization_id=org_id,
                name=secret.name,
                body=SecretUpdate(value="new-value"),
            )

        # MEMBER cannot delete secrets
        with pytest.raises(ForbiddenError):
            non_admin_client.secrets.delete_secret(organization_id=org_id, name=secret.name)
    finally:
        admin_client_.secrets.delete_secret(
            organization_id=org_id, name=secret.name, missing_ok=True
        )


@pytest.mark.cloud
def test_organization_isolation(multi_org_context):
    client_a = JamAI(user_id=multi_org_context.user_a.id)
    client_b = JamAI(user_id=multi_org_context.user_b.id)
    superuser_client = JamAI(user_id=multi_org_context.superuser.id)

    secret_a = client_a.secrets.create_secret(
        body=SecretCreate(name="ORG_A_SECRET", value="org-a-value"),
        organization_id=multi_org_context.org_a.id,
    )
    secret_b = client_b.secrets.create_secret(
        body=SecretCreate(name="ORG_B_SECRET", value="org-b-value"),
        organization_id=multi_org_context.org_b.id,
    )
    secret_super = superuser_client.secrets.create_secret(
        body=SecretCreate(name="SUPERORG_SECRET", value="superorg-value"),
        organization_id=multi_org_context.superorg.id,
    )
    shared_secret_name = "SHARED_SECRET_NAME"

    try:
        assert secret_a.organization_id == multi_org_context.org_a.id
        assert secret_b.organization_id == multi_org_context.org_b.id
        assert secret_super.organization_id == multi_org_context.superorg.id

        # verify org A cannot see org B's secret
        secrets_a = client_a.secrets.list_secrets(organization_id=multi_org_context.org_a.id)
        secrets_b = client_b.secrets.list_secrets(organization_id=multi_org_context.org_b.id)
        secrets_super = superuser_client.secrets.list_secrets(
            organization_id=multi_org_context.superorg.id
        )
        secret_names_a = {s.name for s in secrets_a.items}
        secret_names_b = {s.name for s in secrets_b.items}
        secret_names_super = {s.name for s in secrets_super.items}

        assert secret_a.name in secret_names_a
        assert secret_b.name not in secret_names_a
        assert secret_super.name not in secret_names_a

        assert secret_a.name not in secret_names_b
        assert secret_b.name in secret_names_b
        assert secret_super.name not in secret_names_b

        assert secret_a.name not in secret_names_super
        assert secret_b.name not in secret_names_super
        assert secret_super.name in secret_names_super

        with pytest.raises(ForbiddenError):
            client_a.secrets.get_secret(
                organization_id=multi_org_context.org_b.id, name=secret_b.name
            )
        with pytest.raises(ResourceNotFoundError):
            client_a.secrets.get_secret(
                organization_id=multi_org_context.org_a.id, name=secret_super.name
            )
        with pytest.raises(ResourceNotFoundError):
            client_b.secrets.get_secret(
                organization_id=multi_org_context.org_b.id, name=secret_a.name
            )
        # superuser cannot access secrets from other orgs
        with pytest.raises(ResourceNotFoundError):
            superuser_client.secrets.get_secret(
                organization_id=multi_org_context.superorg.id, name=secret_b.name
            )

        # verify different orgs can have secrets with the same name
        shared_secret_a = client_a.secrets.create_secret(
            body=SecretCreate(name=shared_secret_name, value="org-a-value"),
            organization_id=multi_org_context.org_a.id,
        )
        shared_secret_b = client_b.secrets.create_secret(
            body=SecretCreate(name=shared_secret_name, value="org-b-value"),
            organization_id=multi_org_context.org_b.id,
        )
        shared_secret_super = superuser_client.secrets.create_secret(
            body=SecretCreate(name=shared_secret_name, value="superorg-value"),
            organization_id=multi_org_context.superorg.id,
        )

        assert shared_secret_a.organization_id == multi_org_context.org_a.id
        assert shared_secret_b.organization_id == multi_org_context.org_b.id
        assert shared_secret_super.organization_id == multi_org_context.superorg.id
    finally:
        client_a.secrets.delete_secret(
            organization_id=multi_org_context.org_a.id, name=secret_a.name, missing_ok=True
        )
        client_b.secrets.delete_secret(
            organization_id=multi_org_context.org_b.id, name=secret_b.name, missing_ok=True
        )
        superuser_client.secrets.delete_secret(
            organization_id=multi_org_context.superorg.id, name=secret_super.name, missing_ok=True
        )
        client_a.secrets.delete_secret(
            organization_id=multi_org_context.org_a.id, name=shared_secret_name, missing_ok=True
        )
        client_b.secrets.delete_secret(
            organization_id=multi_org_context.org_b.id, name=shared_secret_name, missing_ok=True
        )
        superuser_client.secrets.delete_secret(
            organization_id=multi_org_context.superorg.id, name=shared_secret_name, missing_ok=True
        )


def test_deduplicate_allowed_projects_with_duplication(admin_client, org_context):
    """Test creating a secret with duplicate projects in allowed_projects list."""
    org_id = org_context.superorg.id
    with (
        create_project(
            dict(name="project1"), user_id=org_context.superuser.id, organization_id=org_id
        ) as proj1,
        create_project(
            dict(name="project2"), user_id=org_context.superuser.id, organization_id=org_id
        ) as proj2,
    ):
        secret = admin_client.secrets.create_secret(
            body=SecretCreate(
                name="DUPLICATE_PROJECTS_SECRET",
                value="test-value",
                allowed_projects=[proj1.id, proj2.id, proj1.id, proj2.id],
            ),
            organization_id=org_context.superorg.id,
        )

        try:
            assert secret.name == "DUPLICATE_PROJECTS_SECRET"
            projects = [proj1.id, proj2.id]
            # verify deduplication
            assert len(secret.allowed_projects) == len(projects)
            assert set(secret.allowed_projects) == set(projects)

            updated_secret = admin_client.secrets.update_secret(
                organization_id=org_context.superorg.id,
                name="DUPLICATE_PROJECTS_SECRET",
                body=SecretUpdate(allowed_projects=[proj2.id, proj2.id, proj1.id]),
            )
            # verify deduplication on update
            assert len(updated_secret.allowed_projects) == len(projects)
            assert set(secret.allowed_projects) == set(projects)
        finally:
            admin_client.secrets.delete_secret(
                organization_id=org_id, name=secret.name, missing_ok=True
            )


def test_allowed_projects_with_nonexistent_project(admin_client, org_context):
    """Test creating a secret with empty string in allowed_projects list."""
    secret_name = "EMPTY_PROJECT_SECRET"
    with (
        create_project(
            dict(name="project1"),
            user_id=org_context.superuser.id,
            organization_id=org_context.superorg.id,
        ) as proj1,
    ):
        try:
            with pytest.raises(
                BadInputError,
                match=r"Non-existing projects are not allowed:",
            ):
                admin_client.secrets.create_secret(
                    body=SecretCreate(
                        name=secret_name,
                        value="test-value",
                        allowed_projects=["", proj1.id],
                    ),
                    organization_id=org_context.superorg.id,
                )

            admin_client.secrets.create_secret(
                body=SecretCreate(
                    name=secret_name,
                    value="test-value",
                    allowed_projects=[proj1.id],
                ),
                organization_id=org_context.superorg.id,
            )
            with pytest.raises(
                BadInputError,
                match=r"Non-existing projects are not allowed:",
            ):
                admin_client.secrets.update_secret(
                    organization_id=org_context.superorg.id,
                    name=secret_name,
                    body=SecretUpdate(allowed_projects=["", proj1.id]),
                )
        finally:
            admin_client.secrets.delete_secret(
                organization_id=org_context.superorg.id, name=secret_name, missing_ok=True
            )


def test_list_pagination_and_search(admin_client, org_context):
    org_id = org_context.superorg.id
    with (
        create_project(
            dict(name="project1"), user_id=org_context.superuser.id, organization_id=org_id
        ) as proj1,
        create_project(
            dict(name="project2"), user_id=org_context.superuser.id, organization_id=org_id
        ) as proj2,
    ):
        data = [
            ("ALPHA", [proj1.id]),
            ("BETA", [proj2.id]),
            ("GAMMA_RAY", None),  # all projects
            ("DELTA_FORCE", []),  # no projects
        ]
        secrets = []
        for name, allowed_projects in data:
            secrets.append(
                admin_client.secrets.create_secret(
                    body=SecretCreate(
                        name=name,
                        value=f"{name}-value",
                        allowed_projects=allowed_projects,
                    ),
                    organization_id=org_id,
                )
            )
        try:
            # test pagination
            page1 = admin_client.secrets.list_secrets(organization_id=org_id, limit=2, offset=0)
            assert len(page1.items) == 2

            page2 = admin_client.secrets.list_secrets(organization_id=org_id, limit=2, offset=2)
            assert len(page2.items) == 2
            assert set(s.name for s in page1.items).isdisjoint(set(s.name for s in page2.items))

            # test search by name
            search_results = admin_client.secrets.list_secrets(
                organization_id=org_id,
                search_query="gamma",  # case-insensitive search
                search_columns=["name"],
            )
            assert len(search_results.items) == 1
            assert search_results.items[0].name == "GAMMA_RAY"

            # test regex char in search
            search_results = admin_client.secrets.list_secrets(
                organization_id=org_id,
                search_query="_",  # case-insensitive search
                search_columns=["name"],
            )
            assert len(search_results.items) == 2
            assert search_results.items[0].name == "GAMMA_RAY"
            assert search_results.items[1].name == "DELTA_FORCE"

            # test empty search query
            search_results = admin_client.secrets.list_secrets(
                organization_id=org_id,
                search_query="",
                search_columns=["name"],
            )
            assert len(search_results.items) == 4
            print(f"search_results.items: {search_results.items}")

            # test search by allowed_projects
            search_results = admin_client.secrets.list_secrets(
                organization_id=org_id,
                search_query=proj1.id,
                search_columns=["allowed_projects"],
            )
            assert len(search_results.items) == 1
            assert search_results.items[0].name == "ALPHA"

            search_results = admin_client.secrets.list_secrets(
                organization_id=org_id,
                search_query="[]",
                search_columns=["allowed_projects"],
            )
            assert len(search_results.items) == 1
            assert search_results.items[0].name == "DELTA_FORCE"
        finally:
            for secret in secrets:
                admin_client.secrets.delete_secret(
                    organization_id=org_id, name=secret.name, missing_ok=True
                )


@pytest.mark.cloud
def test_secret_cascade_delete(admin_client, org_context):
    """Test that secrets are deleted when the organization is deleted."""
    org_id = org_context.superorg.id
    secret_name = "CASCADE_SECRET"

    secret = admin_client.secrets.create_secret(
        body=SecretCreate(name=secret_name, value="to-be-deleted"),
        organization_id=org_id,
    )

    # verify secret exists
    fetched_secret = admin_client.secrets.get_secret(organization_id=org_id, name=secret.name)
    assert fetched_secret.name == secret.name

    with sync_session() as session:
        assert session.get(Secret, (org_id, secret_name)) is not None

    # delete organization
    admin_client.organizations.delete_organization(organization_id=org_id)

    # verify both organization and secret are deleted
    with sync_session() as session:
        org = session.get(Organization, org_id)
        assert org is None

        secret = session.get(Secret, (org_id, secret.name))
        assert secret is None
