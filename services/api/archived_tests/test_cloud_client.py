from typing import Type

import pytest

from owl.cloud_client import Owl
from owl.db import cloud_admin
from owl.protocol import OkResponse

CLIENT_CLS = [Owl]
USER_ID_A = "duncan"
USER_ID_B = "mama"


def _create_user(owl: Owl, user_id: str = USER_ID_A) -> cloud_admin.UserRead:
    response = owl.delete_user(user_id)
    assert isinstance(response, OkResponse)
    user = owl.create_user(
        cloud_admin.UserCreate(
            id=user_id,
            name="Duncan Idaho",
            description="A Ginaz Swordmaster in the service of the honorable House Atreides.",
            email="duncan.idaho@gmail.com",
        )
    )
    return user


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_get_and_list_users(client_cls: Type[Owl]):
    owl = client_cls()
    duncan = _create_user(owl)

    user = owl.get_user(duncan.id)
    assert isinstance(user, cloud_admin.UserRead)
    assert user.id == duncan.id

    users = owl.list_users()
    assert isinstance(users.items, list)
    assert all(isinstance(r, cloud_admin.UserRead) for r in users.items)
    # assert users.total == 5
    assert users.offset == 0
    assert users.limit == 100
    # assert len(users.items) == 5

    response = owl.delete_user(duncan.id)
    assert isinstance(response, OkResponse)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_get_and_list_organizations(client_cls: Type[Owl]):
    owl = client_cls()
    duncan = _create_user(owl)
    company = owl.create_organization(
        cloud_admin.OrganizationCreate(
            creator_user_id=duncan.id,
            name="Company",
            tier=owl.configs.manager.PlanName.free,
            external_keys=dict(openai_api_key="sk-test"),
        )
    )

    org = owl.get_organization(company.id)
    assert isinstance(org, cloud_admin.OrganizationRead)
    assert org.id == company.id

    orgs = owl.list_organizations()
    assert isinstance(orgs.items, list)
    assert all(isinstance(r, cloud_admin.OrganizationRead) for r in orgs.items)
    # assert orgs.total == 5
    assert orgs.offset == 0
    assert orgs.limit == 100
    # assert len(orgs.items) == 5

    response = owl.delete_organization(company.id)
    assert isinstance(response, OkResponse)

    response = owl.delete_user(duncan.id)
    assert isinstance(response, OkResponse)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_create_flow(client_cls: Type[Owl]):
    owl = client_cls()
    response = owl.delete_user(USER_ID_A)
    assert isinstance(response, OkResponse)
    response = owl.delete_user(USER_ID_B)
    assert isinstance(response, OkResponse)
    # response = owl.delete_organization("org_f12d46652cfa3120006e44e2")
    # assert isinstance(response, OkResponse)

    # Create user
    duncan = _create_user(owl)
    print(f"User created: {duncan}\n")

    # Create organization
    company = owl.create_organization(
        cloud_admin.OrganizationCreate(
            creator_user_id=duncan.id,
            name="Company A",
            tier=owl.configs.manager.PlanName.pro,
            external_keys=dict(openai_api_key="sk-test"),
        )
    )
    print(f"Organization created: {company}\n")
    duncan = owl.get_user(duncan.id)

    # Update organization
    company = owl.update_organization(
        cloud_admin.OrganizationUpdate(
            id=company.id,
            name="Company X",
            active=True,
        )
    )
    print(f"Organization updated: {company}\n")
    org = owl.get_organization(company.id)
    assert isinstance(org, cloud_admin.OrganizationRead)
    assert org.id == company.id
    assert org.name == "Company X"

    # Refresh organization quota
    org = owl.refresh_quota(company.id)
    assert isinstance(org, cloud_admin.OrganizationRead)
    original_quota = org.quotas["llm_tokens"]
    print(org.quotas)

    # Create user and link it to existing organization
    mama = owl.create_user(
        cloud_admin.UserCreate(
            id=USER_ID_B,
            name="Mama Idaho",
            description="",
            email="mama.idaho@gmail.com",
        )
    )
    print(f"User created: {mama}\n")
    mama_company = owl.join_organization(
        cloud_admin.UserOrgLinkCreate(
            user_id=mama.id, organization_id=company.id, role=cloud_admin.RoleEnum.member
        )
    )
    print(f"User joined: {mama_company}\n")

    # Submit usage events
    response = owl.add_event(
        cloud_admin.EventCreate(
            id=f"{company.id}_token",
            organization_id=company.id,
            type=owl.configs.manager.ProductType.llm_tokens,
            quota=-0.5,
        )
    )
    assert isinstance(response, OkResponse)
    org = owl.get_organization(company.id)
    assert org.quotas["llm_tokens"] == original_quota - 0.5
    print(f"Organization with LLM token usage: {org}\n")

    response = owl.add_event(
        cloud_admin.EventCreate(
            id=f"{company.id}_credit",
            organization_id=company.id,
            type=owl.configs.manager.ProductType.credit,
            quota=100,
            pending=True,
        )
    )
    assert isinstance(response, OkResponse)
    org = owl.get_organization(company.id)
    assert org.quotas["credit"] == 0
    print(f"Organization with pending credit top-up: {org}\n")

    response = owl.mark_event_as_done(f"{company.id}_credit")
    assert isinstance(response, OkResponse)
    org = owl.get_organization(company.id)
    assert org.quotas["credit"] == 100
    print(f"Organization with completed credit top-up: {org}\n")

    # Fetch specific user
    user = owl.get_user(mama.id)
    print(f"User fetched: {user}\n")

    # Create Project
    project = owl.create_project(
        cloud_admin.ProjectCreate(name="Sales Support", organization_id=company.id)
    )
    print(f"Project created: {project}\n")

    project = owl.create_project(
        cloud_admin.ProjectCreate(name="Insurance", organization_id=company.id)
    )
    print(f"Project created: {project}\n")

    # Delete Project
    response = owl.delete_project(project.id)
    assert isinstance(response, OkResponse)
    print(f"Project deleted: {project}\n")

    # Create API key
    mama_company_key = owl.create_api_key(cloud_admin.ApiKeyCreate(organization_id=company.id))
    print(f"API key created: {mama_company_key}\n")

    # Fetch API key info
    key = owl.get_api_key(mama_company_key.id)
    print(f"API key fetched: {key}\n")

    # Fetch company using API key
    org = owl.get_organization(mama_company_key.id)
    assert isinstance(org, cloud_admin.OrganizationRead)
    print(f"Organization fetched: {org}\n")

    # Delete key
    response = owl.delete_api_key(mama_company_key.id)
    assert isinstance(response, OkResponse)
    print(f"API key deleted: {mama_company_key.id}\n")

    # Leave organization
    response = owl.leave_organization(mama.id, company.id)
    assert isinstance(response, OkResponse)
    org = owl.get_organization(company.id)
    print(f"Organization fetched (mama left): {org}\n")

    orgs = owl.list_organizations()
    assert isinstance(orgs.items, list)
    print(orgs.items)

    # Delete organizations
    duncan = owl.get_user(duncan.id)
    mama = owl.get_user(mama.id)
    for org in duncan.organizations + mama.organizations:
        response = owl.delete_organization(org.organization_id)
        assert isinstance(response, OkResponse)
        print(f"Organization deleted: {org.organization_id}\n")

    # Delete users
    for user_id in [duncan.id, mama.id]:
        response = owl.delete_user(user_id)
        assert isinstance(response, OkResponse)
        print(f"User deleted: {user_id}\n")

    # Check for empty organizations
    orgs = owl.list_organizations()
    for org in orgs.items:
        print(org, "\n")
    assert all(len(org.users) > 0 for org in orgs.items)


if __name__ == "__main__":
    test_create_flow(Owl)
