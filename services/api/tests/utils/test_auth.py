import pytest

from jamaibase import JamAI
from owl.types import OrgMember_, ProjectMember_, Role, UserRead
from owl.utils.auth import has_permissions
from owl.utils.dates import now
from owl.utils.exceptions import AuthorizationError, ForbiddenError

USER_ID = "user_id"
ORG_ID = "0"
PROJ_ID = "project_id"
USER_KWARGS = dict(
    id=USER_ID,
    name="name",
    email="email@example.com",
    organizations=[],
    projects=[],
    created_at=now(),
    updated_at=now(),
    email_verified=True,
    password_hash="***",  # Password is not used in this test
)
ORG_MEMBER_KWARGS = dict(
    user_id=USER_ID,
    organization_id=ORG_ID,
    created_at=now(),
    updated_at=now(),
)
PROJ_MEMBER_KWARGS = dict(
    user_id=USER_ID,
    project_id=PROJ_ID,
    created_at=now(),
    updated_at=now(),
)


@pytest.mark.cloud
def test_has_permissions():
    ### --- ADMIN permissions --- ###
    sys_user = UserRead(
        org_memberships=[OrgMember_(role=Role.ADMIN, **ORG_MEMBER_KWARGS)],
        proj_memberships=[ProjectMember_(role=Role.ADMIN, **PROJ_MEMBER_KWARGS)],
        **USER_KWARGS,
    )
    # Must pass in org ID or proj ID
    with pytest.raises(ValueError):
        has_permissions(sys_user, ["organization"])
    with pytest.raises(ValueError):
        has_permissions(sys_user, ["organization.admin"])
    with pytest.raises(ValueError):
        has_permissions(sys_user, ["project"])
    with pytest.raises(ValueError):
        has_permissions(sys_user, ["project.admin"])
    with pytest.raises(ValueError):
        has_permissions(sys_user, ["organization", "project"], project_id=PROJ_ID)
    with pytest.raises(ValueError):
        has_permissions(sys_user, ["organization", "project"], organization_id=ORG_ID)
    # Membership checks
    assert has_permissions(sys_user, ["system"]) is True
    assert has_permissions(sys_user, ["organization"], organization_id=ORG_ID) is True
    assert has_permissions(sys_user, ["project"], project_id=PROJ_ID) is True
    with pytest.raises(ForbiddenError):
        has_permissions(sys_user, ["organization"], organization_id="ORG_ID")
    with pytest.raises(ForbiddenError):
        has_permissions(sys_user, ["project"], project_id="PROJ_ID")
    assert has_permissions(sys_user, ["organization"], organization_id="ORG_ID", raise_error=False) is False  # fmt: off
    assert has_permissions(sys_user, ["project"], project_id="PROJ_ID", raise_error=False) is False
    # Permission checks
    assert has_permissions(sys_user, ["system.admin"]) is True
    assert has_permissions(sys_user, ["system.member"]) is True
    assert has_permissions(sys_user, ["organization.admin"], organization_id=ORG_ID) is True
    assert has_permissions(sys_user, ["project.admin"], project_id=PROJ_ID) is True

    ### --- MEMBER permissions --- ###
    sys_user = UserRead(
        org_memberships=[OrgMember_(role=Role.MEMBER, **ORG_MEMBER_KWARGS)],
        proj_memberships=[ProjectMember_(role=Role.MEMBER, **PROJ_MEMBER_KWARGS)],
        **USER_KWARGS,
    )
    # Membership checks
    assert has_permissions(sys_user, ["system"]) is True
    assert has_permissions(sys_user, ["organization"], organization_id=ORG_ID) is True
    assert has_permissions(sys_user, ["project"], project_id=PROJ_ID) is True
    # Permission checks
    with pytest.raises(ForbiddenError):
        has_permissions(sys_user, ["system.admin"])
    assert has_permissions(sys_user, ["system.member"]) is True
    assert has_permissions(sys_user, ["system.guest"]) is True
    with pytest.raises(ForbiddenError):
        has_permissions(sys_user, ["organization.admin"], organization_id=ORG_ID)
    assert has_permissions(sys_user, ["organization.member"], organization_id=ORG_ID) is True
    assert has_permissions(sys_user, ["organization.guest"], organization_id=ORG_ID) is True
    with pytest.raises(ForbiddenError):
        has_permissions(sys_user, ["project.admin"], project_id=PROJ_ID)
    assert has_permissions(sys_user, ["project.member"], project_id=PROJ_ID) is True
    assert has_permissions(sys_user, ["project.guest"], project_id=PROJ_ID) is True

    ### --- Update membership --- ###
    user = sys_user.model_copy(deep=True)
    user.org_memberships[0].organization_id = "1"
    assert has_permissions(sys_user, ["system"]) is True
    with pytest.raises(ForbiddenError):
        has_permissions(user, ["system"])
    assert has_permissions(user, ["system", "organization"], organization_id="1") is True
    assert (
        has_permissions(
            user,
            ["system", "organization", "project"],
            organization_id="1",
            project_id="PROJ_ID",
        )
        is True
    )
    with pytest.raises(ForbiddenError):
        has_permissions(
            user,
            ["system", "organization", "project"],
            organization_id="ORG_ID",
            project_id="PROJ_ID",
        )

    ### --- Update permission --- ###
    assert has_permissions(sys_user, ["project.member"], project_id=PROJ_ID) is True
    sys_user.proj_memberships[0].role = Role.GUEST
    with pytest.raises(ForbiddenError):
        has_permissions(sys_user, ["project.member"], project_id=PROJ_ID)
    assert has_permissions(sys_user, ["project.guest"], project_id=PROJ_ID) is True


@pytest.mark.cloud
async def test_no_auth_token():
    client = JamAI(token="")
    with pytest.raises(
        AuthorizationError,
        match='You need to provide your PAT in an "Authorization" header',
    ):
        await client.model_info()
