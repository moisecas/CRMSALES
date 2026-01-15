from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.security import verify_password, create_access_token
from app.models import User

router = APIRouter()

def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=302)

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return request.app.state.templates.TemplateResponse("login.html", {"request": request, "error": None})

@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return request.app.state.templates.TemplateResponse("login.html", {"request": request, "error": "Credenciales inválidas"})

    token = create_access_token(sub=str(user.id), org_id=str(user.org_id), role=user.role)
    resp = _redirect("/")
    resp.set_cookie("access_token", token, httponly=True, samesite="lax")
    return resp

@router.post("/logout")
async def logout():
    resp = _redirect("/login")
    resp.delete_cookie("access_token")
    return resp
