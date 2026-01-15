from fastapi import APIRouter, Depends
from app.dependencies import get_current_user

router = APIRouter(prefix="/ops")

@router.get("/me")
async def me(user=Depends(get_current_user)):
    return {"id": user.id, "org_id": user.org_id, "role": user.role, "email": user.email}
