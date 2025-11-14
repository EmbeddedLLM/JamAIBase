from contextlib import contextmanager
from typing import Generator

from sqlalchemy import NullPool
from sqlmodel import Session, create_engine, delete, select, text

from owl.db.models import (
    Organization,
    OrgMember,
    Project,
    ProjectMember,
)


@contextmanager
def sync_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "postgresql+psycopg://<username>:<pw>@<addr>/jamaibase_owl",
        poolclass=NullPool,
    )
    with Session(engine) as session:
        yield session


def main():
    template_id = "template"
    template_owner = "github|16820751"
    with sync_session() as sess:
        # Re-assign owner
        org = sess.get(Organization, template_id)
        org.owner = template_owner
        org.created_by = template_owner
        sess.add(org)
        sess.commit()
        # Re-build template membership
        sess.exec(delete(OrgMember).where(OrgMember.organization_id == template_id))
        sys_members = sess.exec(select(OrgMember).where(OrgMember.organization_id == "0")).all()
        for m in sys_members:
            sess.add(OrgMember(user_id=m.user_id, organization_id=template_id, role=m.role))
        sess.commit()

        # Get list of orphaned Gen Table schemas
        orphaned = sess.exec(
            text("""
                SELECT
                s.schema_name
                FROM
                information_schema.schemata s
                WHERE
                (
                    s.schema_name LIKE 'proj_%_action' OR
                    s.schema_name LIKE 'proj_%_knowledge' OR
                    s.schema_name LIKE 'proj_%_chat'
                )
                AND NOT EXISTS (
                    -- Check if a project exists with an ID matching the extracted identifier
                    SELECT 1
                    FROM jamai."Project" p
                    WHERE p.id = substring(s.schema_name from '(proj_[^_]+)_')
                )
                ORDER BY
                s.schema_name;
                """)
        ).all()
        project_ids = list({"_".join(o[0].split("_")[:2]) for o in orphaned})
        # Re-create projects
        for project_id in project_ids:
            sess.add(
                Project(
                    id=project_id,
                    name=project_id,
                    organization_id=template_id,
                    created_by=template_owner,
                    owner=template_owner,
                )
            )
            sess.commit()
            for m in sys_members:
                sess.add(ProjectMember(user_id=m.user_id, project_id=project_id, role=m.role))
            sess.commit()


main()
