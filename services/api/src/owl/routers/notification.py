from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from loguru import logger
from pydantic import Field
from sqlmodel import update

from owl.db import AsyncSession, async_session, yield_async_session
from owl.db.models import Notification, NotificationGroup
from owl.types import (
    ListQuery,
    NotificationGroupCreate,
    NotificationGroupRead,
    NotificationRead,
    OkResponse,
    Page,
    UserAuth,
)
from owl.utils.auth import auth_user_service_key, has_permissions
from owl.utils.dates import now
from owl.utils.exceptions import ResourceNotFoundError, handle_exception
from owl.utils.notifications import (
    NotificationIntent,
    dispatch_notification_intent,
)

router = APIRouter()


class ListQueryByUnread(ListQuery):
    unread_only: Annotated[bool, Field(description="Filter unread only.")] = False


@router.post(
    "/v2/notification/group",
    summary="Create a notification group and fan out to recipients.",
    description="Permissions: `system.ADMIN`.",
)
@handle_exception
async def create_notification_group(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    background_tasks: BackgroundTasks,
    body: NotificationGroupCreate,
) -> NotificationGroupRead:
    has_permissions(user, ["system.ADMIN"])
    async with async_session() as session:
        group = NotificationGroup(
            **body.model_dump(exclude={"recipient_ids"}),
        )
        session.add(group)
        await session.commit()
        await session.refresh(group)

    # Fan-out in background
    intent = NotificationIntent(
        audience=body.audience,
        event_type=body.event_type,
        message=body.message,
        actor_id=body.actor_id,
        subject_id=body.subject_id,
        organization_id=body.organization_id,
        project_id=body.project_id,
        recipient_ids=body.recipient_ids,
    )
    background_tasks.add_task(dispatch_notification_intent, intent, group.id)

    logger.bind(
        notif_group_id=group.id,
        event_type=body.event_type,
    ).info(f"Notification group created: {body.event_type} (fan-out scheduled)")
    return NotificationGroupRead.model_validate(group)


@router.get(
    "/v2/notification/group/list",
    summary="List notification groups.",
    description="Permissions: `system.ADMIN`.",
)
@handle_exception
async def list_notification_groups(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    params: Annotated[ListQuery, Query()],
) -> Page[NotificationGroupRead]:
    has_permissions(user, ["system.ADMIN"])
    return await NotificationGroup.list_(
        session=session,
        return_type=NotificationGroupRead,
        offset=params.offset,
        limit=params.limit,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        search_query=params.search_query,
        after=params.after,
    )


@router.get(
    "/v2/notification/group",
    summary="Get a notification group.",
    description="Permissions: `system.ADMIN`.",
)
@handle_exception
async def get_notification_group(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    notification_group_id: Annotated[
        str, Query(min_length=1, description="Notification group ID.")
    ],
) -> NotificationGroupRead:
    has_permissions(user, ["system.ADMIN"])

    group = await session.get(NotificationGroup, notification_group_id)
    if group is None:
        raise ResourceNotFoundError(f'Notification group "{notification_group_id}" is not found.')
    return NotificationGroupRead.model_validate(group)


@router.delete(
    "/v2/notification/group",
    summary="Hard-delete a notification group and all its notifications.",
    description="Permissions: `system.ADMIN`.",
)
@handle_exception
async def delete_notification_group(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    notification_group_id: Annotated[
        str, Query(min_length=1, description="Notification group ID.")
    ],
) -> OkResponse:
    has_permissions(user, ["system.ADMIN"])

    group = await session.get(NotificationGroup, notification_group_id)
    if group is None:
        raise ResourceNotFoundError(f'Notification group "{notification_group_id}" is not found.')
    await session.delete(group)
    await session.commit()
    logger.bind(notif_group_id=notification_group_id).info("Notification group deleted.")
    return OkResponse()


@router.get(
    "/v2/notifications/list",
    summary="List notifications for the current user.",
    description="Permissions: authenticated user.",
)
@handle_exception
async def list_notifications(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    params: Annotated[ListQueryByUnread, Query()],
) -> Page[NotificationRead]:
    return await Notification.list_(
        session=session,
        return_type=NotificationRead,
        offset=params.offset,
        limit=params.limit,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        filters=dict(
            user_id=user.id,
            deleted_at=None,
            **({"opened_at": None} if params.unread_only else {}),
        ),
    )


@router.get(
    "/v2/notifications",
    summary="Get a notification.",
    description="Permissions: notification owner.",
)
@handle_exception
async def get_notification(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    notification_group_id: Annotated[
        str, Query(min_length=1, description="Notification group ID.")
    ],
) -> NotificationRead:
    notif = await session.get(Notification, (user.id, notification_group_id))
    if notif is None or notif.deleted_at is not None:
        raise ResourceNotFoundError("Notification not found.")
    return NotificationRead.model_validate(notif)


@router.delete(
    "/v2/notifications",
    summary="Soft-delete a notification for the current user.",
    description="Permissions: notification owner.",
)
@handle_exception
async def delete_notification(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    notification_group_id: Annotated[
        str, Query(min_length=1, description="Notification group ID.")
    ],
) -> OkResponse:
    notif = await session.get(Notification, (user.id, notification_group_id))
    if notif is None or notif.deleted_at is not None:
        raise ResourceNotFoundError("Notification not found.")
    timestamp = now()
    notif.deleted_at = timestamp
    notif.updated_at = timestamp
    await session.commit()
    return OkResponse()


@router.patch(
    "/v2/notifications/opened",
    summary="Mark one or more notifications as opened.",
    description="Permissions: notification owner.",
)
@handle_exception
async def set_opened(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    notification_group_ids: Annotated[
        list[str], Query(min_length=1, description="List of notification group IDs.")
    ],
) -> OkResponse:
    timestamp = now()
    await session.exec(
        update(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.notification_group_id.in_(notification_group_ids),
            Notification.opened_at.is_(None),
            Notification.deleted_at.is_(None),
        )
        .values(opened_at=timestamp, updated_at=timestamp)
    )
    await session.commit()
    return OkResponse()


@router.patch(
    "/v2/notifications/opened/all",
    summary="Mark all notifications as opened.",
    description="Permissions: authenticated user.",
)
@handle_exception
async def set_all_opened(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
) -> OkResponse:
    timestamp = now()
    await session.exec(
        update(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.opened_at.is_(None),
            Notification.deleted_at.is_(None),
        )
        .values(opened_at=timestamp, updated_at=timestamp)
    )
    await session.commit()
    return OkResponse()
