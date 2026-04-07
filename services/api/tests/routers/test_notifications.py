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
    message: str = "",
    actor_id: str | None = None,
    subject_id: str | None = None,
) -> NotificationGroupRead:
    notif_group = client.notification_groups.create_notification_group(
        NotificationGroupCreate(
            scope=scope,
            event_type=event_type,
            recipient_ids=recipient_ids or [],
            organization_id=organization_id,
            project_id=project_id,
            message=message,
            actor_id=actor_id,
            subject_id=subject_id,
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
            "message": "Welcome to our service!",
        }
        try:
            g1 = _create_notification_group(
                client,
                scope=config["scope"],
                event_type=config["event_type"],
                recipient_ids=[ctx.superuser.id],
                message=config["message"],
            )
            assert isinstance(g1, NotificationGroupRead)
            assert g1.scope == config["scope"]
            assert g1.event_type == config["event_type"]
            assert g1.message == config["message"]
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
            superuser_notifs[0].message
            == user_notifs[0].message
            == "**User** joined organization **System**."
        )

        config2 = {
            "scope": NotificationScope.ORGANIZATION,
            "event_type": NotificationType.ANNOUNCEMENT,
            "message": "Product update: new features released!",
        }
        try:
            g2 = _create_notification_group(
                client,
                scope=config2["scope"],
                event_type=config2["event_type"],
                organization_id=ctx.superorg.id,
                message=config2["message"],
            )
            assert isinstance(g2, NotificationGroupRead)
            assert g2.scope == config2["scope"]
            assert g2.event_type == config2["event_type"]
            assert g2.message == config2["message"]
            # verify both users have the notification
            superuser_notifs = (
                JamAI(user_id=ctx.superuser.id).notifications.list_notifications().items
            )
            user_notifs = JamAI(user_id=ctx.user.id).notifications.list_notifications().items
            assert len(superuser_notifs) == len(user_notifs) == 2
            assert (
                superuser_notifs[0].notification_group_id == user_notifs[0].notification_group_id
            )
            assert superuser_notifs[0].message == user_notifs[0].message == config2["message"]
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
            superuser_notifs[0].message
            == user_notifs[0].message
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
                superuser_notifs[0].message
                == user_notifs[0].message
                == user2_notifs[0].message
                == "**User 2** joined organization **System**."
            )

            config3 = {
                "scope": NotificationScope.PROJECT,
                "event_type": NotificationType.ANNOUNCEMENT,
                "message": "New model available in project!",
            }
            try:
                g3 = _create_notification_group(
                    client,
                    scope=config3["scope"],
                    event_type=config3["event_type"],
                    project_id=project_id,
                    message=config3["message"],
                )
                assert isinstance(g3, NotificationGroupRead)
                assert g3.scope == config3["scope"]
                assert g3.event_type == config3["event_type"]
                assert g3.message == config3["message"]
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
                assert superuser_notifs[0].message == user_notifs[0].message == config3["message"]
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
            "message": "System-wide announcement!",
        }
        with create_user(dict(email="org-user@up.com", name="User 3")) as user3:
            try:
                g4 = _create_notification_group(
                    client,
                    scope=config4["scope"],
                    event_type=config4["event_type"],
                    message=config4["message"],
                )
                assert isinstance(g4, NotificationGroupRead)
                assert g4.scope == config4["scope"]
                assert g4.event_type == config4["event_type"]
                assert g4.message == config4["message"]
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
                    superuser_notifs[0].message
                    == user_notifs[0].message
                    == user3_notifs[0].message
                    == config4["message"]
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
        group = _create_notification_group(client, recipient_ids=[ctx.superuser.id], message="hi")
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
                    client, recipient_ids=[ctx.superuser.id], message=f"msg {i}"
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
        g1 = _create_notification_group(client, recipient_ids=[ctx.superuser.id], message="bye")
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
            client, recipient_ids=[ctx.superuser.id], message="cascade"
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
                        client, recipient_ids=[ctx.superuser.id], message=f"msg {i}"
                    )
                    groups.append(g)
                g_other = _create_notification_group(
                    client, recipient_ids=[other.id], message="for other"
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
    - Get by group ID: verify message, opened_at, deleted_at, nested notification_group.
    - Nonexistent raises ResourceNotFoundError.
    """
    with setup_organizations() as ctx:
        client = _admin_client(ctx.superuser.id)
        user_client = JamAI(user_id=ctx.superuser.id)
        group = _create_notification_group(
            client, recipient_ids=[ctx.superuser.id], message="get me"
        )
        try:
            notif = user_client.notifications.get_notification(group.id)
            assert isinstance(notif, NotificationRead)
            assert notif.user_id == ctx.superuser.id
            assert notif.notification_group_id == group.id
            assert notif.message == "get me"
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
        group = _create_notification_group(client, recipient_ids=[ctx.superuser.id], message="del")
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
    - Mark single notification as opened.
    - Batch mark multiple notifications as opened.
    - Nonexistent/soft-deleted silently skipped (batch semantics).
    """
    with setup_organizations() as ctx:
        client = _admin_client(ctx.superuser.id)
        user_client = JamAI(user_id=ctx.superuser.id)
        groups = []
        try:
            # Mark single opened
            g1 = _create_notification_group(
                client, recipient_ids=[ctx.superuser.id], message="open"
            )
            groups.append(g1)
            resp = user_client.notifications.set_opened(g1.id)
            assert isinstance(resp, OkResponse)
            notif = user_client.notifications.get_notification(g1.id)
            assert notif.opened_at is not None

            # Batch mark opened
            g2 = _create_notification_group(
                client, recipient_ids=[ctx.superuser.id], message="batch1"
            )
            g3 = _create_notification_group(
                client, recipient_ids=[ctx.superuser.id], message="batch2"
            )
            groups.extend([g2, g3])
            resp = user_client.notifications.set_opened([g2.id, g3.id])
            assert isinstance(resp, OkResponse)
            for gid in (g2.id, g3.id):
                notif = user_client.notifications.get_notification(gid)
                assert notif.opened_at is not None

            # Nonexistent silently skipped (batch semantics)
            resp = user_client.notifications.set_opened(["notif_nonexistent"])
            assert isinstance(resp, OkResponse)

            # Soft-deleted silently skipped
            g4 = _create_notification_group(client, recipient_ids=[ctx.superuser.id], message="x")
            groups.append(g4)
            user_client.notifications.delete_notification(g4.id)
            resp = user_client.notifications.set_opened([g4.id])
            assert isinstance(resp, OkResponse)
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
                client, recipient_ids=[ctx.superuser.id], message="keep"
            )
            g2 = _create_notification_group(
                client, recipient_ids=[ctx.superuser.id], message="del"
            )
            g3 = _create_notification_group(
                client, recipient_ids=[ctx.superuser.id], message="also"
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


def test_user_deletion_preserves_notifications():
    """
    - Deleting the actor user sets actor_id to NULL (ON DELETE SET NULL).
    - Deleting the subject user sets subject_id to NULL (ON DELETE SET NULL).
    - Deleting a recipient user cascades their Notification rows only.
    - Other recipients' notifications and the group remain intact.
    """
    with setup_organizations() as ctx:
        client = _admin_client(ctx.superuser.id)
        with create_user(dict(email="actor@test.com", name="Actor")) as actor:
            with create_user(dict(email="subject@test.com", name="Subject")) as subject:
                with create_user(dict(email="recipient@test.com", name="Recipient")) as recipient:
                    # Create group with actor_id and subject_id, fan out to superuser + recipient
                    group = _create_notification_group(
                        client,
                        scope=NotificationScope.USER,
                        event_type=NotificationType.ANNOUNCEMENT,
                        actor_id=actor.id,
                        subject_id=subject.id,
                        recipient_ids=[ctx.superuser.id, recipient.id],
                        message="Test notification for user deletion.",
                    )
                    r_client = JamAI(user_id=recipient.id)

                    try:
                        # Verify initial state
                        assert group.actor_id == actor.id
                        assert group.subject_id == subject.id
                        su_notif = client.notifications.get_notification(group.id)
                        r_notif = r_client.notifications.get_notification(group.id)
                        assert su_notif.notification_group_id == group.id
                        assert r_notif.notification_group_id == group.id

                        # Delete actor: actor_id SET NULL, notifications unaffected
                        JamAI(user_id=actor.id).users.delete_user()
                        group_after = client.notification_groups.get_notification_group(group.id)
                        assert group_after.actor_id is None
                        assert group_after.actor is None
                        assert group_after.subject_id == subject.id  # subject unchanged

                        # Notifications remain accessible
                        su_notif = client.notifications.get_notification(group.id)
                        assert su_notif.notification_group_id == group.id
                        r_notif = r_client.notifications.get_notification(group.id)
                        assert r_notif.notification_group_id == group.id

                        # Delete subject: subject_id SET NULL, notifications unaffected
                        JamAI(user_id=subject.id).users.delete_user()
                        group_after = client.notification_groups.get_notification_group(group.id)
                        assert group_after.subject_id is None
                        assert group_after.subject is None
                        assert group_after.actor_id is None  # null from previous step

                        # Notifications remain accessible
                        su_notif = client.notifications.get_notification(group.id)
                        assert su_notif.notification_group_id == group.id
                        r_notif = r_client.notifications.get_notification(group.id)
                        assert r_notif.notification_group_id == group.id

                        # Delete recipient: recipient's notification CASCADE-deleted
                        JamAI(user_id=recipient.id).users.delete_user()

                        # Notification group still exists
                        group_after = client.notification_groups.get_notification_group(group.id)
                        assert group_after is not None
                        assert group_after.id == group.id

                        # Superuser's notification still intact and listable
                        su_page = client.notifications.list_notifications()
                        assert len(su_page.items) == 1
                        assert su_page.items[0].notification_group_id == group.id

                    finally:
                        client.notification_groups.delete_notification_group(group.id)
