
from dataclasses import dataclass
from fastapi import Depends, Request, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.security import decode_token
from app.models import User

@dataclass
class CurrentUser:
    id: str
    org_id: str
    role: str
    name: str
    email: str

def _get_token(request: Request) -> str | None:
    # web cookie
    t = request.cookies.get("access_token")
    if t:
        return t
    # api bearer
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    token = _get_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")

    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")

    user = (await db.execute(select(User).where(User.id == payload["sub"]))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no existe")

    # defensa extra: coherencia token vs DB
    if str(user.org_id) != str(payload["org_id"]) or user.role != payload["role"]:
        raise HTTPException(status_code=401, detail="Token inconsistente")

    return CurrentUser(
        id=str(user.id),
        org_id=str(user.org_id),
        role=user.role,
        name=user.name,
        email=user.email,
    )

def require_roles(*roles: str):
    async def _check(u: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if u.role not in roles:
            raise HTTPException(status_code=403, detail="No autorizado")
        return u
    return _check
