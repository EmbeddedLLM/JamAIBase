from time import sleep

import pytest

from jamaibase import JamAI
from jamaibase.types import (
    NotificationGroupCreate,
    NotificationGroupRead,
    NotificationRead,
    NotificationScope,
    NotificationType,
    OkResponse,
    Page,
    ProjectCreate,
    Role,
)
from owl.utils.exceptions import ResourceNotFoundError
from owl.utils.test import (
    create_user,
    setup_organizations,
)


def _admin_client(user_id: str = "0") -> JamAI:
    return JamAI(user_id=user_id)


def _create_notification_group(
    client: JamAI,
    *,
    scope: str = NotificationScope.USER,
    event_type: str = NotificationType.ANNOUNCEMENT,
    recipient_ids: list[str] | None = None,
    organization_id: str | None = None,
    project_id: str | None = None,
    meta: dict | None = None,
) -> NotificationGroupRead:
    notif_group = client.notification_groups.create_notification_group(
        NotificationGroupCreate(
            scope=scope,
            event_type=event_type,
            recipient_ids=recipient_ids or [],
            organization_id=organization_id,
            project_id=project_id,
            meta=meta or {},
        )
    )
    sleep(0.5)
    return notif_group


def test_create_notification_group():
    with setup_organizations() as ctx:
        client = _admin_client(ctx.superuser.id)

        # USER scope
        config = {
            "scope": NotificationScope.USER,
            "event_type": NotificationType.MARKETING,
            "meta": {"message": "Welcome to our service!"},
        }
        try:
            g1 = _create_notification_group(
                client,
                scope=config["scope"],
                event_type=config["event_type"],
                recipient_ids=[ctx.superuser.id],
                meta=config["meta"],
            )
            assert isinstance(g1, NotificationGroupRead)
            assert g1.id.startswith("notif_")
            assert g1.scope == config["scope"]
            assert g1.event_type == config["event_type"]
            assert g1.meta == config["meta"]
            # verify user has the notification
            page = JamAI(user_id=ctx.superuser.id).notifications.list_notifications()
            assert len(page.items) == 1
            assert page.items[0].notification_group_id == g1.id
        finally:
            client.notification_groups.delete_notification_group(g1.id)

        # ORG scope — add user to superorg
        client.organizations.join_organization(
            ctx.user.id, organization_id=ctx.superorg.id, role=Role.ADMIN
        )
        sleep(0.5)
        superuser_notifs = JamAI(user_id=ctx.superuser.id).notifications.list_notifications().items
        user_notifs = JamAI(user_id=ctx.user.id).notifications.list_notifications().items
        assert len(superuser_notifs) == len(user_notifs) == 1
        assert superuser_notifs[0].notification_group_id == user_notifs[0].notification_group_id
        assert (
            superuser_notifs[0].body
            == user_notifs[0].body
            == "**User** joined organization **System**."
        )

        config2 = {
            "scope": NotificationScope.ORGANIZATION,
            "event_type": NotificationType.ANNOUNCEMENT,
            "meta": {"message": "Product update: new features released!"},
        }
        try:
            g2 = _create_notification_group(
                client,
                scope=config2["scope"],
                event_type=config2["event_type"],
                organization_id=ctx.superorg.id,
                meta=config2["meta"],
            )
            assert isinstance(g2, NotificationGroupRead)
            assert g2.scope == config2["scope"]
            assert g2.event_type == config2["event_type"]
            assert g2.meta == config2["meta"]
            # verify both users have the notification
            superuser_notifs = (
                JamAI(user_id=ctx.superuser.id).notifications.list_notifications().items
            )
            user_notifs = JamAI(user_id=ctx.user.id).notifications.list_notifications().items
            assert len(superuser_notifs) == len(user_notifs) == 2
            assert (
                superuser_notifs[0].notification_group_id == user_notifs[0].notification_group_id
            )
            assert superuser_notifs[0].body == user_notifs[0].body == config2["meta"]["message"]
        finally:
            client.notification_groups.delete_notification_group(g2.id)

        # PROJECT scope — add user2 to superorg's project
        project = client.projects.create_project(
            ProjectCreate(
                organization_id=ctx.superorg.id,
                name="Project Notif",
            )
        )
        project_id = project.id
        client.projects.join_project(ctx.user.id, project_id=project_id, role=Role.ADMIN)
        sleep(0.5)
        superuser_notifs = JamAI(user_id=ctx.superuser.id).notifications.list_notifications().items
        user_notifs = JamAI(user_id=ctx.user.id).notifications.list_notifications().items
        assert len(superuser_notifs) == len(user_notifs) == 2
        assert superuser_notifs[0].notification_group_id == user_notifs[0].notification_group_id
        assert (
            superuser_notifs[0].body
            == user_notifs[0].body
            == "**User** joined project **Project Notif**."
        )

        # create user2, add to org but not project
        with create_user(dict(email="org-user@up.com", name="User 2")) as user2:
            client.organizations.join_organization(
                user2.id, organization_id=ctx.superorg.id, role=Role.ADMIN
            )
            sleep(0.5)
            superuser_notifs = (
                JamAI(user_id=ctx.superuser.id).notifications.list_notifications().items
            )
            user_notifs = JamAI(user_id=ctx.user.id).notifications.list_notifications().items
            user2_notifs = JamAI(user_id=user2.id).notifications.list_notifications().items
            assert len(superuser_notifs) == len(user_notifs) == 3
            assert len(user2_notifs) == 1
            assert (
                superuser_notifs[0].notification_group_id
                == user_notifs[0].notification_group_id
                == user2_notifs[0].notification_group_id
            )
            assert (
                superuser_notifs[0].body
                == user_notifs[0].body
                == user2_notifs[0].body
                == "**User 2** joined organization **System**."
            )

            config3 = {
                "scope": NotificationScope.PROJECT,
                "event_type": NotificationType.ANNOUNCEMENT,
                "meta": {"message": "New model available in project!"},
            }
            try:
                g3 = _create_notification_group(
                    client,
                    scope=config3["scope"],
                    event_type=config3["event_type"],
                    project_id=project_id,
                    meta=config3["meta"],
                )
                assert isinstance(g3, NotificationGroupRead)
                assert g3.scope == config3["scope"]
                assert g3.event_type == config3["event_type"]
                assert g3.meta == config3["meta"]
                # verify first 2 users get the notification
                superuser_notifs = (
                    JamAI(user_id=ctx.superuser.id).notifications.list_notifications().items
                )
                user_notifs = JamAI(user_id=ctx.user.id).notifications.list_notifications().items
                assert len(superuser_notifs) == len(user_notifs) == 4
                assert (
                    superuser_notifs[0].notification_group_id
                    == user_notifs[0].notification_group_id
                    == g3.id
                )
                assert (
                    superuser_notifs[0].body == user_notifs[0].body == config3["meta"]["message"]
                )
                # verify user2 doesn't receive the notification
                user2_notifs = JamAI(user_id=user2.id).notifications.list_notifications().items
                assert len(user2_notifs) == 1
                assert not any(n.notification_group_id == g3.id for n in user2_notifs)
            finally:
                client.notification_groups.delete_notification_group(g3.id)

        # System scope - user3 should get it even without org membership
        config4 = {
            "scope": NotificationScope.SYSTEM,
            "event_type": NotificationType.ANNOUNCEMENT,
            "meta": {"message": "System-wide announcement!"},
        }
        with create_user(dict(email="org-user@up.com", name="User 3")) as user3:
            try:
                g4 = _create_notification_group(
                    client,
                    scope=config4["scope"],
                    event_type=config4["event_type"],
                    meta=config4["meta"],
                )
                assert isinstance(g4, NotificationGroupRead)
                assert g4.scope == config4["scope"]
                assert g4.event_type == config4["event_type"]
                assert g4.meta == config4["meta"]
                # verify all 3 users get the notification
                superuser_notifs = (
                    JamAI(user_id=ctx.superuser.id).notifications.list_notifications().items
                )
                user_notifs = JamAI(user_id=ctx.user.id).notifications.list_notifications().items
                user3_notifs = JamAI(user_id=user3.id).notifications.list_notifications().items
                assert len(superuser_notifs) == len(user_notifs) == 4
                assert len(user3_notifs) == 1
                assert (
                    superuser_notifs[0].notification_group_id
                    == user_notifs[0].notification_group_id
                    == user3_notifs[0].notification_group_id
                    == g4.id
                )
                assert (
                    superuser_notifs[0].body
                    == user_notifs[0].body
                    == user3_notifs[0].body
                    == config4["meta"]["message"]
                )
            finally:
                client.notification_groups.delete_notification_group(g4.id)


def test_get_notification_group():
    """
    - Get by ID returns correct group.
    - Nonexistent ID raises ResourceNotFoundError.
    """
    with setup_organizations() as ctx:
        client = _admin_client(ctx.superuser.id)
        group = _create_notification_group(
            client, recipient_ids=[ctx.superuser.id], meta={"message": "hi"}
        )
        try:
            fetched = client.notification_groups.get_notification_group(group.id)
            assert isinstance(fetched, NotificationGroupRead)
            assert fetched.id == group.id
            assert fetched.event_type == group.event_type

            with pytest.raises(ResourceNotFoundError):
                client.notification_groups.get_notification_group("notif_nonexistent")
        finally:
            client.notification_groups.delete_notification_group(group.id)


def test_list_notification_groups():
    """Pagination: limit, total, default descending order."""
    with setup_organizations() as ctx:
        client = _admin_client(ctx.superuser.id)
        groups = []
        try:
            for i in range(3):
                g = _create_notification_group(
                    client, recipient_ids=[ctx.superuser.id], meta={"message": f"msg {i}"}
                )
                groups.append(g)

            page = client.notification_groups.list_notification_groups(limit=2)
            assert isinstance(page, Page)
            assert len(page.items) == 2
            assert page.total == 3
            assert page.items[0].created_at >= page.items[1].created_at
        finally:
            for g in groups:
                client.notification_groups.delete_notification_group(g.id)


def test_delete_notification_group():
    """
    - Hard-delete removes the group.
    - missing_ok=True on nonexistent returns OkResponse.
    - Cascade: deleting group also removes per-user notifications.
    """
    with setup_organizations() as ctx:
        client = _admin_client(ctx.superuser.id)
        user_client = JamAI(user_id=ctx.superuser.id)

        # Hard-delete
        g1 = _create_notification_group(
            client, recipient_ids=[ctx.superuser.id], meta={"message": "bye"}
        )
        resp = client.notification_groups.delete_notification_group(g1.id)
        assert isinstance(resp, OkResponse)
        with pytest.raises(ResourceNotFoundError):
            client.notification_groups.get_notification_group(g1.id)

        # missing_ok
        resp = client.notification_groups.delete_notification_group(
            "notif_nonexistent", missing_ok=True
        )
        assert isinstance(resp, OkResponse)

        # Cascade
        g2 = _create_notification_group(
            client, recipient_ids=[ctx.superuser.id], meta={"message": "cascade"}
        )
        notif = user_client.notifications.get_notification(g2.id)
        assert isinstance(notif, NotificationRead)
        client.notification_groups.delete_notification_group(g2.id)
        with pytest.raises(ResourceNotFoundError):
            user_client.notifications.get_notification(g2.id)


def test_list_notifications():
    """
    - User only sees their own notifications.
    - unread_only filter excludes opened notifications.
    - Pagination: offset/limit, no overlap, beyond-range returns empty.
    """
    with setup_organizations() as ctx:
        with create_user(dict(email="notif-other@test.com", name="Other")) as other:
            client = _admin_client(ctx.superuser.id)
            user_client = JamAI(user_id=ctx.superuser.id)
            groups = []
            try:
                # Create 5 for superuser, 1 for other
                for i in range(5):
                    g = _create_notification_group(
                        client, recipient_ids=[ctx.superuser.id], meta={"message": f"msg {i}"}
                    )
                    groups.append(g)
                g_other = _create_notification_group(
                    client, recipient_ids=[other.id], meta={"message": "for other"}
                )
                groups.append(g_other)

                # User only sees own
                page = user_client.notifications.list_notifications()
                assert all(n.user_id == ctx.superuser.id for n in page.items)
                assert not any(n.notification_group_id == g_other.id for n in page.items)

                # unread_only
                user_client.notifications.set_opened(groups[0].id)
                page = user_client.notifications.list_notifications(unread_only=True)
                group_ids = [n.notification_group_id for n in page.items]
                assert groups[0].id not in group_ids
                assert groups[1].id in group_ids

                # Pagination
                page1 = user_client.notifications.list_notifications(offset=0, limit=2)
                assert len(page1.items) == 2
                assert page1.total == 5

                page2 = user_client.notifications.list_notifications(offset=2, limit=2)
                assert len(page2.items) == 2
                ids1 = {n.notification_group_id for n in page1.items}
                ids2 = {n.notification_group_id for n in page2.items}
                assert ids1.isdisjoint(ids2)

                # Beyond range
                page3 = user_client.notifications.list_notifications(offset=100, limit=10)
                assert len(page3.items) == 0
            finally:
                for g in groups:
                    client.notification_groups.delete_notification_group(g.id)


def test_get_notification():
    """
    - Get by group ID: verify body, opened_at, deleted_at, nested notification_group.
    - Nonexistent raises ResourceNotFoundError.
    """
    with setup_organizations() as ctx:
        client = _admin_client(ctx.superuser.id)
        user_client = JamAI(user_id=ctx.superuser.id)
        group = _create_notification_group(
            client, recipient_ids=[ctx.superuser.id], meta={"message": "get me"}
        )
        try:
            notif = user_client.notifications.get_notification(group.id)
            assert isinstance(notif, NotificationRead)
            assert notif.user_id == ctx.superuser.id
            assert notif.notification_group_id == group.id
            assert notif.body == "get me"
            assert notif.opened_at is None
            assert notif.deleted_at is None
            assert notif.notification_group.id == group.id
            assert notif.notification_group.event_type == NotificationType.ANNOUNCEMENT

            with pytest.raises(ResourceNotFoundError):
                user_client.notifications.get_notification("notif_nonexistent")
        finally:
            client.notification_groups.delete_notification_group(group.id)


def test_delete_notification():
    """
    - Soft-delete hides notification from list and get.
    - Double soft-delete raises ResourceNotFoundError.
    """
    with setup_organizations() as ctx:
        client = _admin_client(ctx.superuser.id)
        user_client = JamAI(user_id=ctx.superuser.id)
        group = _create_notification_group(
            client, recipient_ids=[ctx.superuser.id], meta={"message": "del"}
        )
        try:
            resp = user_client.notifications.delete_notification(group.id)
            assert isinstance(resp, OkResponse)

            # Hidden from get
            with pytest.raises(ResourceNotFoundError):
                user_client.notifications.get_notification(group.id)

            # Hidden from list
            page = user_client.notifications.list_notifications()
            assert not any(n.notification_group_id == group.id for n in page.items)

            # Double delete
            with pytest.raises(ResourceNotFoundError):
                user_client.notifications.delete_notification(group.id)
        finally:
            client.notification_groups.delete_notification_group(group.id)


def test_set_opened():
    """
    - Mark opened: opened_at is set.
    - Nonexistent raises ResourceNotFoundError.
    - Soft-deleted raises ResourceNotFoundError.
    """
    with setup_organizations() as ctx:
        client = _admin_client(ctx.superuser.id)
        user_client = JamAI(user_id=ctx.superuser.id)
        groups = []
        try:
            # Mark opened
            g1 = _create_notification_group(
                client, recipient_ids=[ctx.superuser.id], meta={"message": "open"}
            )
            groups.append(g1)
            resp = user_client.notifications.set_opened(g1.id)
            assert isinstance(resp, OkResponse)
            notif = user_client.notifications.get_notification(g1.id)
            assert notif.opened_at is not None

            # Nonexistent
            with pytest.raises(ResourceNotFoundError):
                user_client.notifications.set_opened("notif_nonexistent")

            # Soft-deleted
            g2 = _create_notification_group(
                client, recipient_ids=[ctx.superuser.id], meta={"message": "x"}
            )
            groups.append(g2)
            user_client.notifications.delete_notification(g2.id)
            with pytest.raises(ResourceNotFoundError):
                user_client.notifications.set_opened(g2.id)
        finally:
            for g in groups:
                client.notification_groups.delete_notification_group(g.id)


def test_set_all_opened():
    """
    - Marks all unread notifications as opened.
    - Does not resurrect soft-deleted notifications.
    """
    with setup_organizations() as ctx:
        client = _admin_client(ctx.superuser.id)
        user_client = JamAI(user_id=ctx.superuser.id)
        groups = []
        try:
            g1 = _create_notification_group(
                client, recipient_ids=[ctx.superuser.id], meta={"message": "keep"}
            )
            g2 = _create_notification_group(
                client, recipient_ids=[ctx.superuser.id], meta={"message": "del"}
            )
            g3 = _create_notification_group(
                client, recipient_ids=[ctx.superuser.id], meta={"message": "also"}
            )
            groups.extend([g1, g2, g3])

            user_client.notifications.delete_notification(g2.id)
            resp = user_client.notifications.set_all_opened()
            assert isinstance(resp, OkResponse)

            # All remaining are opened
            page = user_client.notifications.list_notifications(unread_only=True)
            assert page.total == 0

            # g1 and g3 are opened
            for gid in (g1.id, g3.id):
                notif = user_client.notifications.get_notification(gid)
                assert notif.opened_at is not None

            # g2 still soft-deleted
            with pytest.raises(ResourceNotFoundError):
                user_client.notifications.get_notification(g2.id)
        finally:
            for g in groups:
                client.notification_groups.delete_notification_group(g.id)


def test_body_template():
    """
    - ANNOUNCEMENT: {message} substitution.
    - ORG_INVITATION: actor_name and org_name substitution.
    """
    with setup_organizations() as ctx:
        client = _admin_client(ctx.superuser.id)
        user_client = JamAI(user_id=ctx.superuser.id)
        groups = []
        try:
            # ANNOUNCEMENT
            g1 = _create_notification_group(
                client,
                event_type=NotificationType.ANNOUNCEMENT,
                recipient_ids=[ctx.superuser.id],
                meta={"message": "System maintenance at 2am UTC."},
            )
            groups.append(g1)
            notif = user_client.notifications.get_notification(g1.id)
            assert notif.body == "System maintenance at 2am UTC."

            # ORG_INVITATION
            g2 = _create_notification_group(
                client,
                event_type=NotificationType.ORG_INVITATION,
                recipient_ids=[ctx.superuser.id],
                meta={"actor_name": "Alice", "org_name": "Acme Corp", "role": "MEMBER"},
            )
            groups.append(g2)
            notif = user_client.notifications.get_notification(g2.id)
            assert (
                notif.body
                == "**Alice** invited you to join organization **Acme Corp** with role **MEMBER**."
            )
        finally:
            for g in groups:
                client.notification_groups.delete_notification_group(g.id)
