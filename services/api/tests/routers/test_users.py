import httpx
import pytest
from pwdlib import PasswordHash

from jamaibase import JamAI
from jamaibase.types import (
    OkResponse,
    Page,
    PasswordChangeRequest,
    PasswordLoginRequest,
    UserRead,
)
from jamaibase.utils.exceptions import (
    AuthorizationError,
    BadInputError,
    ForbiddenError,
    ResourceExistsError,
    ResourceNotFoundError,
)
from owl.utils.test import (
    EMAIL,
    create_organization,
    create_user,
    register_password,
    setup_organizations,
    setup_projects,
)

# --- Auth --- #

PASSWORD = "test_password"


def test_register_password():
    with register_password(dict(email=EMAIL, name="Carl", password=PASSWORD)):
        pass


def test_login_password():
    with register_password(dict(email=EMAIL, name="Carl", password=PASSWORD)):
        user = JamAI().auth.login_password(PasswordLoginRequest(email=EMAIL, password=PASSWORD))
        assert isinstance(user, UserRead)


def test_login_password_wrong_pw():
    with register_password(dict(email=EMAIL, name="Carl", password=PASSWORD)):
        user = JamAI().auth.login_password(PasswordLoginRequest(email=EMAIL, password=PASSWORD))
        assert isinstance(user, UserRead)
        # Wrong password should fail
        with pytest.raises(AuthorizationError):
            JamAI().auth.login_password(PasswordLoginRequest(email=EMAIL, password="PASSWORD"))


def test_login_password_hash():
    with register_password(dict(email=EMAIL, name="Carl", password=PASSWORD)):
        user = JamAI().auth.login_password(PasswordLoginRequest(email=EMAIL, password=PASSWORD))
        assert isinstance(user, UserRead)
        # Password hash should fail
        hasher = PasswordHash.recommended()
        password_hash = hasher.hash(PASSWORD)
        with pytest.raises((AuthorizationError, BadInputError)):
            JamAI().auth.login_password(dict(email=EMAIL, password=password_hash))


def test_change_password():
    with register_password(dict(email=EMAIL, name="Carl", password=PASSWORD)):
        # Existing password OK
        user = JamAI().auth.login_password(PasswordLoginRequest(email=EMAIL, password=PASSWORD))
        assert isinstance(user, UserRead)
        # Change password
        user = JamAI(user_id=user.id).auth.change_password(
            PasswordChangeRequest(email=EMAIL, password=PASSWORD, new_password=PASSWORD * 2)
        )
        assert isinstance(user, UserRead)
        # Old password should fail
        with pytest.raises(AuthorizationError):
            JamAI().auth.login_password(PasswordLoginRequest(email=EMAIL, password=PASSWORD))
        # New password OK
        user = JamAI().auth.login_password(
            PasswordLoginRequest(email=EMAIL, password=PASSWORD * 2)
        )
        assert isinstance(user, UserRead)


@pytest.mark.cloud
def test_change_password_wrong_user():
    with (
        register_password(dict(email=EMAIL, name="Carl", password=PASSWORD)) as u0,
        register_password(dict(email="russell@up.com", name="Russell", password="test")) as u1,
    ):
        # Existing password OK
        user = JamAI().auth.login_password(PasswordLoginRequest(email=EMAIL, password=PASSWORD))
        assert user.id == u0.id
        # Wrong user should fail
        with pytest.raises(ForbiddenError):
            JamAI(user_id=u1.id).auth.change_password(
                PasswordChangeRequest(email=EMAIL, password="PASSWORD", new_password=PASSWORD * 2)
            )
        # Old password OK
        user = JamAI().auth.login_password(PasswordLoginRequest(email=EMAIL, password=PASSWORD))
        assert user.id == u0.id
        # New password should fail
        with pytest.raises(AuthorizationError):
            JamAI().auth.login_password(PasswordLoginRequest(email=EMAIL, password=PASSWORD * 2))


def test_change_password_wrong_old_pw():
    with register_password(dict(email=EMAIL, name="Carl", password=PASSWORD)):
        # Existing password OK
        user = JamAI().auth.login_password(PasswordLoginRequest(email=EMAIL, password=PASSWORD))
        assert isinstance(user, UserRead)
        # Wrong old password should fail
        with pytest.raises(AuthorizationError):
            JamAI(user_id=user.id).auth.change_password(
                PasswordChangeRequest(email=EMAIL, password="PASSWORD", new_password=PASSWORD * 2)
            )
        # Old password OK
        user = JamAI().auth.login_password(PasswordLoginRequest(email=EMAIL, password=PASSWORD))
        assert isinstance(user, UserRead)
        # New password should fail
        with pytest.raises(AuthorizationError):
            JamAI().auth.login_password(PasswordLoginRequest(email=EMAIL, password=PASSWORD * 2))


# --- Users --- #


def test_create_superuser():
    with create_user(dict(email=EMAIL, name="Carl", password="test_password")) as user:
        assert user.id == "0"
        assert user.email == EMAIL
        assert isinstance(user.password_hash, str)
        assert user.password_hash == "***"


def test_create_user():
    with (
        create_user(),
        create_user(
            dict(email="russell@up.com", name="Russell", password="test_password")
        ) as user,
    ):
        assert user.id != "0"
        assert isinstance(user.password_hash, str)
        assert user.password_hash == "***"


def test_create_user_existing_id():
    with create_user(), create_user(dict(email="russell@up.com", name="Russell")) as user:
        with pytest.raises(ResourceExistsError):
            with create_user(dict(id=user.id, email="random@up.com", name="Random")):
                pass


def test_create_user_existing_email():
    with (
        create_user(dict(email=EMAIL, name="Carl", password=PASSWORD)) as user,
    ):
        with pytest.raises(ResourceExistsError, match="email"):
            with create_user(dict(email=user.email, name="Random")):
                pass


def test_get_list_users():
    relations = {"org_memberships", "proj_memberships", "organizations", "projects"}
    dump_kwargs = dict(warnings="error", exclude=relations)
    with (
        # Create users with name ordering opposite of creation order
        # Also test case sensitivity
        create_user(dict(email="russell@up.com", name="Russell")) as superuser,
        create_user(
            dict(email="carl@up.com", name="carl", google_id="1234", github_id="22")
        ) as u1,
        create_user(dict(email="aaron@up.com", name="Aaron")) as u2,
        create_organization(user_id=superuser.id),
    ):
        super_client = JamAI(user_id=superuser.id)
        ### --- List users --- ###
        num_users = 3
        users = super_client.users.list_users()
        assert isinstance(users, Page)
        assert len(users.items) == num_users
        assert users.total == num_users
        assert all(isinstance(m, UserRead) for m in users.items)
        assert users.items[0].id == superuser.id
        assert users.items[1].id == u1.id

        ### --- Get user --- ###
        for u in users.items:
            _user = super_client.users.get_user(u.id)
            assert isinstance(_user, UserRead)
            u = u.model_dump(**dump_kwargs)
            _user = _user.model_dump(**dump_kwargs)
            assert _user == u, f"Data mismatch: {_user=}, {u=}"
        # Fetch using Google ID
        _user = super_client.users.get_user(f"google-oauth2|{u1.google_id}")
        assert isinstance(_user, UserRead)
        u = u1.model_dump(**dump_kwargs)
        _user = _user.model_dump(**dump_kwargs)
        assert _user == u, f"Data mismatch: {_user=}, {u=}"
        # Fetch using GitHub ID
        _user = super_client.users.get_user(f"github|{u1.github_id}")
        assert isinstance(_user, UserRead)
        u = u1.model_dump(**dump_kwargs)
        _user = _user.model_dump(**dump_kwargs)
        assert _user == u, f"Data mismatch: {_user=}, {u=}"

        ### --- List users (offset and limit) --- ###
        _users = super_client.users.list_users(offset=0, limit=1)
        assert len(_users.items) == 1
        assert _users.total == num_users
        assert _users.items[0].id == users.items[0].id, f"{_users.items=}"
        _users = super_client.users.list_users(offset=1, limit=1)
        assert len(_users.items) == 1
        assert _users.total == num_users
        assert _users.items[0].id == users.items[1].id, f"{_users.items=}"
        # Offset >= num rows
        _users = super_client.users.list_users(offset=num_users, limit=1)
        assert len(_users.items) == 0
        assert _users.total == num_users
        _users = super_client.users.list_users(offset=num_users + 1, limit=1)
        assert len(_users.items) == 0
        assert _users.total == num_users
        # Invalid offset and limit
        with pytest.raises(BadInputError):
            super_client.users.list_users(offset=0, limit=0)
        with pytest.raises(BadInputError):
            super_client.users.list_users(offset=-1, limit=1)

        ### --- List users (order_by and order_ascending) --- ###
        _users = super_client.users.list_users(order_ascending=False)
        assert len(users.items) == num_users
        assert _users.total == num_users
        assert [t.id for t in _users.items[::-1]] == [t.id for t in users.items]
        _users = super_client.users.list_users(order_by="name")
        assert len(users.items) == num_users
        assert _users.total == num_users
        assert [t.id for t in _users.items[::-1]] == [t.id for t in users.items]
        assert [t.name for t in _users.items] == [u2.name, u1.name, superuser.name]
        _users = super_client.users.list_users(order_by="name", order_ascending=False)
        assert len(users.items) == num_users
        assert _users.total == num_users
        assert [t.id for t in _users.items] == [t.id for t in users.items]

        ### --- List users (search_query and search_columns) --- ###
        _users = super_client.users.list_users(search_query="rus")
        assert len(_users.items) == 1
        assert _users.total == 1
        assert _users.total != num_users
        assert _users.items[0].id == superuser.id
        _users = super_client.users.list_users(search_query="rus", offset=1)
        assert len(_users.items) == 0
        assert _users.total == 1


@pytest.mark.cloud
def test_list_users_permission():
    with create_user(), create_user(dict(email="russell@up.com", name="Russell")) as user:
        with pytest.raises(ForbiddenError):
            JamAI(user_id=user.id).users.list_users()


def test_get_nonexistent_user():
    with setup_organizations() as ctx:
        client = JamAI(user_id=ctx.superuser.id)
        response = client.users.get_user(ctx.user.id)
        assert isinstance(response, UserRead)
        with pytest.raises(ResourceNotFoundError):
            client.users.get_user("fake")


def test_update_user():
    with create_user() as user:
        client = JamAI(user_id=user.id)
        new_name = f"{user.name} {user.name}"
        response = client.users.update_user(dict(name=new_name))
        assert isinstance(response, UserRead)
        assert response.name == new_name
        assert response.model_dump(
            exclude={"updated_at", "name", "preferred_name"}
        ) == user.model_dump(exclude={"updated_at", "name", "preferred_name"})
        assert response.updated_at > user.updated_at


def test_delete_user():
    with (
        create_user() as superuser,
        create_user(dict(email="russell@up.com", name="Russell")) as user,
        create_organization(user_id=superuser.id),
    ):
        client = JamAI(user_id=superuser.id)
        # Fetch
        response = client.users.get_user(user.id)
        assert isinstance(response, UserRead)
        # Delete
        response = JamAI(user_id=user.id).users.delete_user(missing_ok=False)
        assert isinstance(response, OkResponse)
        assert response.ok is True
        # Fetch again
        with pytest.raises(ResourceNotFoundError):
            client.users.get_user(user.id)


def test_cors():
    def _assert_cors(_response: httpx.Response):
        assert "Access-Control-Allow-Origin" in _response.headers, _response.headers
        assert "Access-Control-Allow-Methods" in _response.headers, _response.headers
        assert "Access-Control-Allow-Headers" in _response.headers, _response.headers
        assert "Access-Control-Allow-Credentials" in _response.headers, _response.headers
        assert _response.headers["Access-Control-Allow-Credentials"].lower() == "true"

    with setup_projects() as ctx:
        client = JamAI(user_id=ctx.superuser.id)

        headers = {
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        }

        # Preflight
        response = httpx.options(client.api_base, headers=headers)
        _assert_cors(response)
        print(response.headers)

        endpoint = f"{client.api_base}/v1/models"
        # Assert preflight no auth
        response = httpx.options(endpoint, headers=headers)
        _assert_cors(response)
        # Assert CORS headers in methods with auth
        response = httpx.get(
            endpoint,
            headers={
                "Authorization": "Bearer PAT_KEY",
                **headers,
            },
        )
        assert response.status_code == 401
        assert "Access-Control-Allow-Origin" in response.headers, response.headers
        assert "Access-Control-Allow-Credentials" in response.headers, response.headers
        assert response.headers["Access-Control-Allow-Credentials"].lower() == "true"
