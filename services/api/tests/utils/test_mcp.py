from contextlib import asynccontextmanager
from dataclasses import dataclass

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import (
    CallToolResult,
    ClientNotification,
    EmptyResult,
    InitializedNotification,
    ListToolsResult,
)

from jamaibase import JamAIAsync
from jamaibase.types import (
    OrganizationCreate,
    Page,
    ProjectRead,
    Role,
)
from owl.configs import ENV_CONFIG
from owl.utils.test import (
    create_organization,
    create_project,
    create_user,
)


@dataclass(slots=True)
class SetupContext:
    superorg_id: str
    org_id: str
    superproject_id: str
    project_id: str
    superuser_id: str
    user_id: str
    guestuser_id: str


@pytest.fixture(scope="module")
async def setup():
    with (
        # Create superuser
        create_user() as superuser,
        # Create user
        create_user({"email": "testuser@example.com", "name": "Test User"}) as user,
        # Create guestuser
        create_user({"email": "guest@example.com", "name": "Test Guest User"}) as guestuser,
        # Create super organization
        create_organization(
            body=OrganizationCreate(name="Clubhouse"), user_id=superuser.id
        ) as superorg,
        # Create organization
        create_organization(body=OrganizationCreate(name="CommonOrg"), user_id=user.id) as org,
        # Create project
        create_project(
            dict(name="projA"), user_id=superuser.id, organization_id=superorg.id
        ) as p0,
        create_project(dict(name="projA"), user_id=user.id, organization_id=org.id) as p1,
    ):
        client = JamAIAsync(user_id=user.id)
        # guest user join organization but not project
        await client.organizations.join_organization(
            user_id=guestuser.id, organization_id=org.id, role=Role.MEMBER
        )
        yield SetupContext(
            superorg_id=superorg.id,
            org_id=org.id,
            superproject_id=p0.id,
            project_id=p1.id,
            superuser_id=superuser.id,
            user_id=user.id,
            guestuser_id=guestuser.id,
        )


@asynccontextmanager
async def mcp_session(user_id: str, project_id: str | None = None):
    # Connect to a streamable HTTP server
    headers = {
        "X-USER-ID": user_id,
        "X-PROJECT-ID": project_id if project_id else "",
    }
    if ENV_CONFIG.is_cloud:
        headers["Authorization"] = f"Bearer {ENV_CONFIG.service_key_plain}"
    async with streamablehttp_client(
        url=f"http://localhost:{ENV_CONFIG.port}/api/v1/mcp/http",
        headers=headers,
    ) as (read_stream, write_stream, _):
        # Create a session using the client streams
        async with ClientSession(read_stream, write_stream) as session:
            # Initialize the connection
            await session.initialize()
            yield session


async def test_send_ping(setup: SetupContext):
    async with mcp_session(setup.superuser_id) as session:
        response = await session.send_ping()
        assert isinstance(response, EmptyResult)


async def test_send_notification(setup: SetupContext):
    async with mcp_session(setup.superuser_id) as session:
        response = await session.send_notification(
            ClientNotification(InitializedNotification(method="notifications/initialized"))
        )
        assert response is None


async def test_list_tools(setup: SetupContext):
    async with mcp_session(setup.superuser_id) as session:
        tool_list = await session.list_tools()
        assert isinstance(tool_list, ListToolsResult)
        tools = {tool.name: tool for tool in tool_list.tools}
        # Should have all tools available
        assert (
            "list_organizations_api_v2_organizations_list_get" in tools
        )  # need system membership
        assert "model_info_api_v1_models_get" in tools  # need project membership
        assert "create_project_api_v2_projects_post" in tools  # needs organization.admin
        assert (
            "create_action_table_api_v2_gen_tables_action_post" in tools
        )  # needs organization or project member permission
        assert (
            "create_conversation_api_v2_conversations_post" in tools
        )  # needs project member permission
        assert (
            "list_projects_api_v2_projects_list_get" in tools
        )  # need system or organization guest permission

    async with mcp_session(setup.user_id) as session:
        tool_list = await session.list_tools()
        assert isinstance(tool_list, ListToolsResult)
        tools = {tool.name: tool for tool in tool_list.tools}
        assert "model_info_api_v1_models_get" in tools  # need project membership
        assert "create_project_api_v2_projects_post" in tools  # needs organization.admin
        assert (
            "create_action_table_api_v2_gen_tables_action_post" in tools
        )  # needs organization or project member permission
        assert (
            "create_conversation_api_v2_conversations_post" in tools
        )  # needs project member permission
        assert (
            "list_projects_api_v2_projects_list_get" in tools
        )  # need system or organization guest permission

    async with mcp_session(setup.guestuser_id) as session:
        tool_list = await session.list_tools()
        assert isinstance(tool_list, ListToolsResult)
        tools = {tool.name: tool for tool in tool_list.tools}
        assert "model_info_api_v1_models_get" not in tools  # need project membership
        assert "create_project_api_v2_projects_post" not in tools  # needs organization.admin
        assert (
            "create_action_table_api_v2_gen_tables_action_post" in tools
        )  # needs organization or project member permission
        assert (
            "create_conversation_api_v2_conversations_post" not in tools
        )  # needs project member permission
        assert (
            "list_projects_api_v2_projects_list_get" in tools
        )  # need system or organization guest permission


@pytest.mark.cloud
async def test_list_tools_system_membership(setup: SetupContext):
    async with mcp_session(setup.superuser_id) as session:
        tool_list = await session.list_tools()
        assert isinstance(tool_list, ListToolsResult)
        tools = {tool.name: tool for tool in tool_list.tools}
        # Should have all tools available
        assert (
            "list_organizations_api_v2_organizations_list_get" in tools
        )  # need system membership

    async with mcp_session(setup.user_id) as session:
        tool_list = await session.list_tools()
        assert isinstance(tool_list, ListToolsResult)
        tools = {tool.name: tool for tool in tool_list.tools}
        assert (
            "list_organizations_api_v2_organizations_list_get" not in tools
        )  # need system membership

    async with mcp_session(setup.guestuser_id) as session:
        tool_list = await session.list_tools()
        assert isinstance(tool_list, ListToolsResult)
        tools = {tool.name: tool for tool in tool_list.tools}
        assert (
            "list_organizations_api_v2_organizations_list_get" not in tools
        )  # need system membership


async def test_call_tool(setup: SetupContext):
    async with mcp_session(setup.superuser_id) as session:
        # List projects
        tool_result = await session.call_tool(
            "list_projects_api_v2_projects_list_get",
            dict(
                organization_id=setup.superorg_id,
                limit=2,
                order_by="created_at",
                order_ascending=False,
            ),
        )
        assert isinstance(tool_result, CallToolResult)
        assert not tool_result.isError
        assert isinstance(tool_result.content[0].text, str)
        projects = Page[ProjectRead].model_validate_json(tool_result.content[0].text)
        assert projects.total == 1
        assert projects.items[0].id == setup.superproject_id
        # Create Proj
        new_proj_name = "MCP proj"
        tool_result = await session.call_tool(
            "create_project_api_v2_projects_post",
            dict(organization_id=setup.superorg_id, name=new_proj_name),
        )
        assert isinstance(tool_result, CallToolResult)
        assert isinstance(tool_result.content[0].text, str)
        proj = ProjectRead.model_validate_json(tool_result.content[0].text)
        assert proj.organization.id == setup.superorg_id
        assert proj.name == new_proj_name
    # Fetch the updated organization
    client = JamAIAsync(user_id=setup.superuser_id)
    p = await client.projects.get_project(proj.id)
    assert isinstance(p, ProjectRead)
    assert p.name == new_proj_name
