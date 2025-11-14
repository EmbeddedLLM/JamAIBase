import pytest

from jamaibase import JamAI
from jamaibase.types import OrganizationCreate, TableType
from owl.utils.exceptions import ResourceNotFoundError
from owl.utils.test import (
    create_organization,
    create_project,
    create_user,
    list_tables,
)


def test_get_list_tables_no_schema():
    with (
        create_user() as superuser,
        create_organization(
            body=OrganizationCreate(name="Clubhouse"), user_id=superuser.id
        ) as superorg,
        # Create project
        create_project(
            dict(name="Project"), user_id=superuser.id, organization_id=superorg.id
        ) as p0,
    ):
        super_client = JamAI(user_id=superuser.id, project_id=p0.id)
        # No gen table schema
        for table_type in TableType:
            tables = list_tables(super_client, table_type)
            assert len(tables.items) == 0
            assert tables.total == 0
            with pytest.raises(ResourceNotFoundError, match="Table .+ is not found."):
                super_client.table.get_table(table_type, "123")
