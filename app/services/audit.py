import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AuditLog

async def log_audit(
    db: AsyncSession,
    org_id: str,
    actor_user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    meta: dict | None = None,
):
    db.add(AuditLog(
        org_id=uuid.UUID(org_id),
        actor_user_id=uuid.UUID(actor_user_id) if actor_user_id else None,
        action=action,
        entity_type=entity_type,
        entity_id=uuid.UUID(entity_id),
        meta=meta,
    ))
