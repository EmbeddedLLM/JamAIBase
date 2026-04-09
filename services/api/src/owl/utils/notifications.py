from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import text

from owl.db import SCHEMA, async_session
from owl.db.models import NotificationGroup
from owl.types import NotificationAudience, NotificationType, ProductType, Role
from owl.utils.dates import now

# Mapping from ProductType to NotificationType for limit alerts
_PRODUCT_TO_NOTIFICATION_TYPE: dict[ProductType, NotificationType] = {
    ProductType.LLM_TOKENS: NotificationType.LLM_TOKEN_LIMIT,
    ProductType.IMAGE_TOKENS: NotificationType.IMAGE_TOKEN_LIMIT,
    ProductType.EMBEDDING_TOKENS: NotificationType.EMBEDDING_TOKEN_LIMIT,
    ProductType.RERANKER_SEARCHES: NotificationType.RERANKER_LIMIT,
    ProductType.DB_STORAGE: NotificationType.DB_STORAGE_LIMIT,
    ProductType.FILE_STORAGE: NotificationType.FILE_STORAGE_LIMIT,
    ProductType.EGRESS: NotificationType.EGRESS_LIMIT,
}

# Unit labels for each product type (used in notification body)
_PRODUCT_UNIT: dict[ProductType, str] = {
    ProductType.LLM_TOKENS: "Mtok",
    ProductType.IMAGE_TOKENS: "Mtok",
    ProductType.EMBEDDING_TOKENS: "Mtok",
    ProductType.RERANKER_SEARCHES: "Ksearch",
    ProductType.DB_STORAGE: "GiB",
    ProductType.FILE_STORAGE: "GiB",
    ProductType.EGRESS: "GiB",
}

_PRODUCT_LABEL: dict[ProductType, str] = {
    ProductType.LLM_TOKENS: "LLM token",
    ProductType.IMAGE_TOKENS: "Image token",
    ProductType.EMBEDDING_TOKENS: "Embedding token",
    ProductType.RERANKER_SEARCHES: "Reranker",
    ProductType.DB_STORAGE: "DB storage",
    ProductType.FILE_STORAGE: "File storage",
    ProductType.EGRESS: "Egress",
}

QUOTA_ALERT_THRESHOLDS = (50, 80, 100)


@dataclass(frozen=True, slots=True)
class NotificationIntent:
    """Plain data carrier for a notification to be dispatched in the background."""

    audience: NotificationAudience
    event_type: NotificationType
    message: str
    actor_id: str | None = None
    subject_id: str | None = None
    organization_id: str | None = None
    project_id: str | None = None
    recipient_ids: list[str] = field(default_factory=list)
    notif_admin_only: bool = False


async def _fan_out_notifications(
    session,
    *,
    group_id: str,
    message: str,
    audience: NotificationAudience,
    organization_id: str | None = None,
    project_id: str | None = None,
    recipient_ids: list[str] | None = None,
    notif_admin_only: bool = False,
) -> int:
    """INSERT...SELECT fan-out. Returns number of rows inserted."""
    base_cols = f'{SCHEMA}."Notification" (user_id, notification_group_id, message, meta, created_at, updated_at)'
    base_vals = ":group_id, :message, '{}'::jsonb, :ts, :ts"
    params: dict = dict(group_id=group_id, message=message, ts=now())

    if audience == NotificationAudience.ORGANIZATION:
        where = "om.organization_id = :org_id"
        params["org_id"] = organization_id
        if notif_admin_only:
            where += " AND om.role = :role"
            params["role"] = Role.ADMIN.value
        sql = f'INSERT INTO {base_cols} SELECT om.user_id, {base_vals} FROM {SCHEMA}."OrgMember" om WHERE {where}'

    elif audience == NotificationAudience.PROJECT:
        where = "pm.project_id = :proj_id"
        params["proj_id"] = project_id
        if notif_admin_only:
            where += " AND pm.role = :role"
            params["role"] = Role.ADMIN.value
        sql = f'INSERT INTO {base_cols} SELECT pm.user_id, {base_vals} FROM {SCHEMA}."ProjectMember" pm WHERE {where}'

    elif audience == NotificationAudience.USER:
        params["user_ids"] = recipient_ids or []
        sql = f'INSERT INTO {base_cols} SELECT u.id, {base_vals} FROM {SCHEMA}."User" u WHERE u.id = ANY(:user_ids)'

    elif audience == NotificationAudience.SYSTEM:
        sql = f'INSERT INTO {base_cols} SELECT u.id, {base_vals} FROM {SCHEMA}."User" u'

    else:
        return 0

    result = await session.exec(text(sql), params=params)
    return result.rowcount


async def dispatch_notification_intent(
    intent: NotificationIntent,
    group_id: str | None = None,
) -> None:
    """Background task: create NotificationGroup (if needed) + fan-out via INSERT...SELECT."""
    try:
        async with async_session() as session:
            if group_id is None:
                group = NotificationGroup(
                    audience=intent.audience,
                    event_type=intent.event_type,
                    organization_id=intent.organization_id,
                    project_id=intent.project_id,
                    actor_id=intent.actor_id,
                    subject_id=intent.subject_id,
                    message=intent.message,
                )
                session.add(group)
                await session.flush()
                group_id = group.id

            row_count = await _fan_out_notifications(
                session,
                group_id=group_id,
                message=intent.message,
                audience=intent.audience,
                organization_id=intent.organization_id,
                project_id=intent.project_id,
                recipient_ids=intent.recipient_ids,
                notif_admin_only=intent.notif_admin_only,
            )
            await session.commit()

            if row_count == 0:
                logger.warning(
                    f"No recipients resolved for notification {intent.event_type} "
                    f"(audience={intent.audience}, org={intent.organization_id}, proj={intent.project_id})"
                )
            else:
                logger.bind(
                    notif_group_id=group_id,
                    event_type=intent.event_type,
                    recipients=row_count,
                ).info(f"Notification created: {intent.event_type} -> {row_count} recipients")

    except Exception:
        logger.exception(f"Failed to create notification for event type {intent.event_type}")


def notify_org_invitation(
    *,
    actor_id: str,
    actor_name: str,
    invitee_user_id: str,
    organization_id: str,
    org_name: str,
    role: str,
) -> NotificationIntent:
    return NotificationIntent(
        audience=NotificationAudience.USER,
        event_type=NotificationType.ORG_INVITATION,
        message=f"**{actor_name}** invited you to join organization **{org_name}** with role **{role}**.",
        actor_id=actor_id,
        subject_id=invitee_user_id,
        organization_id=organization_id,
        recipient_ids=[invitee_user_id],
    )


def notify_project_invitation(
    *,
    actor_id: str,
    actor_name: str,
    invitee_user_id: str,
    project_id: str,
    project_name: str,
    organization_id: str,
    role: str,
) -> NotificationIntent:
    return NotificationIntent(
        audience=NotificationAudience.USER,
        event_type=NotificationType.PROJECT_INVITATION,
        message=f"**{actor_name}** invited you to join project **{project_name}** with role **{role}**.",
        actor_id=actor_id,
        subject_id=invitee_user_id,
        organization_id=organization_id,
        project_id=project_id,
        recipient_ids=[invitee_user_id],
    )


def notify_org_invitation_revoked(
    *,
    actor_id: str,
    actor_name: str,
    invitee_user_id: str,
    organization_id: str,
    org_name: str,
) -> NotificationIntent:
    return NotificationIntent(
        audience=NotificationAudience.USER,
        event_type=NotificationType.ORG_INVITATION_REVOKED,
        message=f"**{actor_name}** revoked your invitation to organization **{org_name}**.",
        actor_id=actor_id,
        subject_id=invitee_user_id,
        organization_id=organization_id,
        recipient_ids=[invitee_user_id],
    )


def notify_project_invitation_revoked(
    *,
    actor_id: str,
    actor_name: str,
    invitee_user_id: str,
    project_id: str,
    project_name: str,
    organization_id: str,
) -> NotificationIntent:
    return NotificationIntent(
        audience=NotificationAudience.USER,
        event_type=NotificationType.PROJECT_INVITATION_REVOKED,
        message=f"**{actor_name}** revoked your invitation to project **{project_name}**.",
        actor_id=actor_id,
        subject_id=invitee_user_id,
        organization_id=organization_id,
        project_id=project_id,
        recipient_ids=[invitee_user_id],
    )


def notify_org_member_joined(
    *,
    organization_id: str,
    org_name: str,
    subject_id: str,
    subject_name: str,
) -> NotificationIntent:
    return NotificationIntent(
        audience=NotificationAudience.ORGANIZATION,
        event_type=NotificationType.ORG_MEMBER_JOINED,
        message=f"**{subject_name}** joined organization **{org_name}**.",
        subject_id=subject_id,
        organization_id=organization_id,
    )


def notify_project_member_joined(
    *,
    project_id: str,
    project_name: str,
    organization_id: str,
    subject_id: str,
    subject_name: str,
) -> NotificationIntent:
    return NotificationIntent(
        audience=NotificationAudience.PROJECT,
        event_type=NotificationType.PROJECT_MEMBER_JOINED,
        message=f"**{subject_name}** joined project **{project_name}**.",
        subject_id=subject_id,
        organization_id=organization_id,
        project_id=project_id,
    )


def notify_org_role_updated(
    *,
    actor_id: str,
    actor_name: str,
    target_user_id: str,
    organization_id: str,
    org_name: str,
    role: str,
) -> NotificationIntent:
    return NotificationIntent(
        audience=NotificationAudience.USER,
        event_type=NotificationType.ORG_ROLE_UPDATED,
        message=f"**{actor_name}** changed your role to **{role}** in organization **{org_name}**.",
        actor_id=actor_id,
        subject_id=target_user_id,
        organization_id=organization_id,
        recipient_ids=[target_user_id],
    )


def notify_project_role_updated(
    *,
    actor_id: str,
    actor_name: str,
    target_user_id: str,
    project_id: str,
    project_name: str,
    organization_id: str,
    role: str,
) -> NotificationIntent:
    return NotificationIntent(
        audience=NotificationAudience.USER,
        event_type=NotificationType.PROJECT_ROLE_UPDATED,
        message=f"**{actor_name}** changed your role to **{role}** in project **{project_name}**.",
        actor_id=actor_id,
        subject_id=target_user_id,
        organization_id=organization_id,
        project_id=project_id,
        recipient_ids=[target_user_id],
    )


def notify_org_owner_updated(
    *,
    actor_id: str,
    actor_name: str,
    organization_id: str,
    org_name: str,
    subject_id: str,
    subject_name: str,
) -> NotificationIntent:
    return NotificationIntent(
        audience=NotificationAudience.ORGANIZATION,
        event_type=NotificationType.ORG_OWNER_UPDATED,
        message=f"**{actor_name}** transferred ownership of organization **{org_name}** to **{subject_name}**.",
        actor_id=actor_id,
        subject_id=subject_id,
        organization_id=organization_id,
    )


def notify_project_owner_updated(
    *,
    actor_id: str,
    actor_name: str,
    project_id: str,
    project_name: str,
    organization_id: str,
    subject_id: str,
    subject_name: str,
) -> NotificationIntent:
    return NotificationIntent(
        audience=NotificationAudience.PROJECT,
        event_type=NotificationType.PROJECT_OWNER_UPDATED,
        message=f"**{actor_name}** transferred ownership of project **{project_name}** to **{subject_name}**.",
        actor_id=actor_id,
        subject_id=subject_id,
        organization_id=organization_id,
        project_id=project_id,
    )


def notify_quota_limit(
    *,
    organization_id: str,
    product_type: ProductType,
    threshold: int,
    usage: float,
    quota: float,
) -> NotificationIntent:
    unit = _PRODUCT_UNIT[product_type]
    event_type = _PRODUCT_TO_NOTIFICATION_TYPE[product_type]
    label = _PRODUCT_LABEL[product_type]
    return NotificationIntent(
        audience=NotificationAudience.ORGANIZATION,
        event_type=event_type,
        message=f"{label} usage has reached **{threshold}%** of quota ({usage:,.2f}/{quota:,.2f} {unit}).",
        organization_id=organization_id,
        notif_admin_only=False,
    )


def check_quota_thresholds(
    *,
    organization_id: str,
    old_usage: float,
    new_usage: float,
    quota: float | None,
    product_type: ProductType,
    quota_alert_thresholds: tuple[int, ...] = QUOTA_ALERT_THRESHOLDS,
) -> list[tuple[int, NotificationIntent]]:
    """Return (threshold, NotificationIntent) pairs for any quota thresholds crossed."""
    if quota is None or quota <= 0:
        return []
    old_pct = old_usage / quota * 100
    new_pct = new_usage / quota * 100
    results = []
    for threshold in quota_alert_thresholds:
        if old_pct < threshold <= new_pct:
            results.append(
                (
                    threshold,
                    notify_quota_limit(
                        organization_id=organization_id,
                        product_type=product_type,
                        threshold=threshold,
                        usage=new_usage,
                        quota=quota,
                    ),
                )
            )
    return results
