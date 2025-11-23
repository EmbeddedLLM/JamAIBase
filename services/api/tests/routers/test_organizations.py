import pytest

from jamaibase import JamAI
from jamaibase.types import (
    OrganizationRead,
    OrganizationUpdate,
    OrgMemberRead,
    Page,
)
from owl.configs import ENV_CONFIG
from owl.db import TEMPLATE_ORG_ID, sync_session
from owl.db.models import Organization
from owl.types import ChatCompletionResponse, ChatRequest, Role, StripePaymentInfo
from owl.utils.exceptions import (
    BadInputError,
    ForbiddenError,
    ResourceNotFoundError,
    UpgradeTierError,
)
from owl.utils.test import (
    BASE_PLAN_ID,
    ELLM_DESCRIBE_CONFIG,
    ELLM_DESCRIBE_DEPLOYMENT,
    GPT_4O_MINI_CONFIG,
    GPT_4O_MINI_DEPLOYMENT,
    GPT_41_NANO_CONFIG,
    GPT_41_NANO_DEPLOYMENT,
    create_deployment,
    create_model_config,
    create_organization,
    create_user,
    setup_organizations,
    setup_projects,
)


def test_create_superorg():
    """
    Test creating organizations
    - Assert that superorg and template org are created
    - Assert that external keys are persisted correctly
    """
    with (
        create_user() as superuser,
        create_organization(
            dict(name="Clubhouse", external_keys={"key": "value", "openai": "openai"}),
            user_id=superuser.id,
        ) as superorg,
    ):
        with create_organization(
            dict(name="Clubhouse", external_keys={"key": "value", "openai": "openai"}),
            user_id=superuser.id,
        ) as org:
            assert superorg.id == "0"
            assert superorg.name == "Clubhouse"
            assert superorg.external_keys == {"key": "value", "openai": "openai"}
            assert org.id != "0"
            assert org.name == "Clubhouse"
            assert org.external_keys == {"key": "value", "openai": "openai"}
            # Check org memberships
            user = JamAI(user_id=superuser.id).users.get_user(superuser.id)
            assert len(user.org_memberships) == 3  # Superorg + Template + Org
            org_memberships = {m.organization_id: m for m in user.org_memberships}
            assert org_memberships["0"].role == Role.ADMIN
            assert org_memberships[TEMPLATE_ORG_ID].role == Role.ADMIN
            assert org_memberships[org.id].role == Role.ADMIN

        # Assert template org and sys org still exist
        with sync_session() as session:
            assert session.get(Organization, TEMPLATE_ORG_ID) is not None
            assert session.get(Organization, "0") is not None
    # Assert template org and sys org are deleted
    with sync_session() as session:
        assert session.get(Organization, TEMPLATE_ORG_ID) is None
        assert session.get(Organization, "0") is None


# @pytest.mark.cloud
# def test_create_superorg_permission():
#     with create_user(), create_user(dict(email="russell@up.com", name="Russell")) as user:
#         with pytest.raises(ForbiddenError):
#             with create_organization(user_id=user.id):
#                 pass


@pytest.mark.cloud
def test_create_organization_base_tier_limit():
    """
    A user can only have one organization with a base tier plan.
    """
    with (
        create_user() as superuser,
        create_user(dict(name="user", email="russell@up.com")) as user,
        # Internal org "0" is not counted against the limit
        create_organization(dict(name="Admin org"), user_id=superuser.id) as superorg,
        # First base tier org
        create_organization(dict(name="Org 1"), user_id=superuser.id) as o1,
    ):
        assert superorg.id == "0"
        assert o1.id != "0"
        # Auto-subscribed to base tier plan
        assert o1.price_plan_id == BASE_PLAN_ID
        # Second base tier org
        with pytest.raises(
            (ForbiddenError, UpgradeTierError),
            match="can have only one organization with Free Plan",
        ):
            with create_organization(dict(name="Org 2"), user_id=superuser.id):
                pass
        # Create another org with a different plan
        super_client = JamAI(user_id=superuser.id)
        client = JamAI(user_id=user.id)
        with (
            create_organization(
                dict(name="Org 2"), user_id=superuser.id, subscribe_plan=False
            ) as o2,
            create_organization(dict(name="Org X"), user_id=user.id, subscribe_plan=False) as ox,
        ):
            assert o2.price_plan_id is None
            assert o2.active is False
            plans = super_client.prices.list_price_plans().items
            plan = next((p for p in plans if p.id != BASE_PLAN_ID), None)
            assert plan is not None
            invoice = super_client.organizations.subscribe_plan(
                organization_id=o2.id, price_plan_id=plan.id
            )
            assert isinstance(invoice, StripePaymentInfo)
            assert invoice.amount_due == 0  # Stripe not enabled
            # Second base tier org
            with pytest.raises(
                (ForbiddenError, UpgradeTierError),
                match="can have only one organization with Free Plan",
            ):
                with create_organization(dict(name="Org 3"), user_id=superuser.id):
                    pass
            # Cannot subscribe to base tier plan
            with pytest.raises(
                (ForbiddenError, UpgradeTierError),
                match="can have only one organization with Free Plan",
            ):
                super_client.organizations.subscribe_plan(
                    organization_id=o2.id, price_plan_id=BASE_PLAN_ID
                )
            # Auto-subscribed to base tier plan
            assert ox.price_plan_id == BASE_PLAN_ID
            with pytest.raises(BadInputError, match="already subscribed to .+ plan"):
                client.organizations.subscribe_plan(
                    organization_id=ox.id, price_plan_id=BASE_PLAN_ID
                )


def test_list_organizations():
    with setup_organizations() as ctx:
        orgs = JamAI(user_id=ctx.superuser.id).organizations.list_organizations()
        assert isinstance(orgs, Page)
        assert len(orgs.items) == 3  # 2 orgs + template
        assert orgs.total == 3


@pytest.mark.cloud
def test_list_organizations_permission():
    with setup_organizations() as ctx:
        with pytest.raises(ForbiddenError):
            JamAI(user_id=ctx.user.id).organizations.list_organizations()


def test_get_org():
    """
    Test fetch organization.
    - Admin can view API keys
    - Member cannot view API keys
    - System user can fetch org but not API keys
    """
    with setup_organizations() as ctx:
        super_client = JamAI(user_id=ctx.superuser.id)
        client = JamAI(user_id=ctx.user.id)
        # Add API key
        super_client.organizations.update_organization(
            ctx.superorg.id, OrganizationUpdate(external_keys=dict(x="x"))
        )
        client.organizations.update_organization(
            ctx.org.id, OrganizationUpdate(external_keys=dict(x="x"))
        )
        # Join organization as member
        membership = super_client.organizations.join_organization(
            ctx.user.id,
            organization_id=ctx.superorg.id,
            role=Role.MEMBER,
        )
        assert isinstance(membership, OrgMemberRead)
        # Admin can view API keys
        org = super_client.organizations.get_organization(ctx.superorg.id)
        assert isinstance(org, OrganizationRead)
        assert org.id == ctx.superorg.id
        assert org.external_keys["x"] == "x"
        # Member cannot view API keys (cloud only)
        org = client.organizations.get_organization(ctx.superorg.id)
        assert isinstance(org, OrganizationRead)
        assert org.id == ctx.superorg.id
        assert org.external_keys["x"] == "x" if ENV_CONFIG.is_oss else "***"
        # System user can fetch org but not API keys (cloud only)
        user = super_client.users.get_user()
        assert ctx.org.id not in {m.organization_id for m in user.org_memberships}
        org = super_client.organizations.get_organization(ctx.org.id)
        assert isinstance(org, OrganizationRead)
        assert org.id == ctx.org.id
        assert org.external_keys["x"] == "x" if ENV_CONFIG.is_oss else "***"


def test_update_org():
    """
    Test update organization.
    - Partial update org
    - Partial update external keys
    """
    with setup_organizations() as ctx:
        client = JamAI(user_id=ctx.user.id)
        # Partial update org
        org = client.organizations.update_organization(
            ctx.org.id, OrganizationUpdate(name="Updated Name")
        )
        assert isinstance(org, OrganizationRead)
        assert org.name == "Updated Name"
        assert org.timezone is None
        org = client.organizations.update_organization(
            ctx.org.id, OrganizationUpdate(timezone="Asia/Kuala_Lumpur")
        )
        assert isinstance(org, OrganizationRead)
        assert org.name == "Updated Name"
        assert org.timezone == "Asia/Kuala_Lumpur"
        with pytest.raises(BadInputError, match="timezone"):
            # Strict timezone validation
            client.organizations.update_organization(
                ctx.org.id, dict(timezone="asia/kuala_lumpur")
            )
        # Update external keys
        org = client.organizations.update_organization(
            ctx.org.id, OrganizationUpdate(external_keys=dict(x="x"))
        )
        assert isinstance(org, OrganizationRead)
        assert org.external_keys == dict(x="x")
        org = client.organizations.update_organization(
            ctx.org.id, OrganizationUpdate(external_keys=dict(y="y"))
        )
        assert isinstance(org, OrganizationRead)
        assert org.external_keys == dict(y="y")


@pytest.mark.cloud
def test_update_org_permission():
    """
    Test update organization.
    - Only admin can update org
    """
    with setup_organizations() as ctx:
        super_client = JamAI(user_id=ctx.superuser.id)
        client = JamAI(user_id=ctx.user.id)
        # Test update permission
        membership = client.organizations.join_organization(
            ctx.superuser.id,
            organization_id=ctx.org.id,
            role=Role.MEMBER,
        )
        assert isinstance(membership, OrgMemberRead)
        # Member fail
        with pytest.raises(ForbiddenError):
            super_client.organizations.update_organization(
                ctx.org.id, OrganizationUpdate(name="New Name")
            )
        # Admin OK
        org = client.organizations.update_organization(
            ctx.org.id, OrganizationUpdate(name="New Name")
        )
        assert isinstance(org, OrganizationRead)
        assert org.name == "New Name"


def test_delete_org():
    with setup_organizations() as ctx:
        ok_response = JamAI(user_id=ctx.user.id).organizations.delete_organization(
            ctx.org.id, missing_ok=False
        )
        assert ok_response.ok is True
        client = JamAI(user_id=ctx.superuser.id)
        with pytest.raises(ResourceNotFoundError):
            client.organizations.get_organization(ctx.org.id)
        # Assert users are not deleted
        users = client.users.list_users()
        assert isinstance(users, Page)
        assert len(users.items) == 2


@pytest.mark.cloud
def test_delete_org_permission():
    with setup_organizations() as ctx:
        client = JamAI(user_id=ctx.user.id)
        with pytest.raises(ForbiddenError):
            client.organizations.delete_organization(ctx.superorg.id, missing_ok=False)


def test_organisation_model_catalogue():
    """
    Test listing model configs:
    - System level
    - Organization level
    - Private models via allow list and block list
    - Run chat completion
    """
    with setup_projects() as ctx:
        with (
            # Common models
            create_model_config(GPT_4O_MINI_CONFIG) as m0,
            # Private models (allow list)
            create_model_config(
                dict(
                    **ELLM_DESCRIBE_CONFIG.model_dump(exclude_unset=True),
                    allowed_orgs=[ctx.org.id],
                )
            ) as m1,
            # Private models (block list)
            create_model_config(
                dict(
                    **GPT_41_NANO_CONFIG.model_dump(exclude_unset=True),
                    allowed_orgs=[ctx.org.id, ctx.superorg.id],
                    blocked_orgs=[ctx.org.id],
                )
            ) as m2,
            create_deployment(GPT_4O_MINI_DEPLOYMENT),
            create_deployment(ELLM_DESCRIBE_DEPLOYMENT),
            create_deployment(GPT_41_NANO_DEPLOYMENT),
        ):
            assert m0.is_private is False
            assert m1.is_private is True
            assert m2.is_private is True
            super_client = JamAI(user_id=ctx.superuser.id, project_id=ctx.projects[0].id)
            client = JamAI(user_id=ctx.user.id, project_id=ctx.projects[1].id)
            # System-level
            models = super_client.models.list_model_configs()
            assert isinstance(models, Page)
            assert len(models.items) == 3
            assert models.total == 3
            # Organisation-level
            models = super_client.organizations.model_catalogue(organization_id=ctx.superorg.id)
            assert isinstance(models, Page)
            assert len(models.items) == 2
            assert models.total == 2
            model_ids = {m.id for m in models.items}
            assert GPT_4O_MINI_CONFIG.id in model_ids
            assert ELLM_DESCRIBE_CONFIG.id not in model_ids
            assert GPT_41_NANO_CONFIG.id in model_ids
            # Organisation-level
            models = client.organizations.model_catalogue(organization_id=ctx.org.id)
            assert isinstance(models, Page)
            assert len(models.items) == 2
            assert models.total == 2
            model_ids = {m.id for m in models.items}
            assert GPT_4O_MINI_CONFIG.id in model_ids
            assert ELLM_DESCRIBE_CONFIG.id in model_ids
            assert GPT_41_NANO_CONFIG.id not in model_ids
            # Run chat completion
            req = ChatRequest(
                model=ELLM_DESCRIBE_CONFIG.id,
                messages=[{"role": "user", "content": "Hi there"}],
                max_tokens=4,
                stream=False,
            )
            response = client.generate_chat_completions(req)
            assert isinstance(response, ChatCompletionResponse)
            assert len(response.content) > 0
            assert response.prompt_tokens == 2
            assert response.completion_tokens > 0
            with pytest.raises(ResourceNotFoundError):
                super_client.generate_chat_completions(req)


if __name__ == "__main__":
    test_list_organizations()
