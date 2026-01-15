import uuid
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import Category, Product
from app.services.audit import log_audit

router = APIRouter(prefix="/categories")

def r(url: str):
    return RedirectResponse(url, status_code=302)

@router.get("", response_class=HTMLResponse)
async def list_categories(request: Request, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    rows = (await db.execute(
        select(Category).where(Category.org_id == uuid.UUID(user.org_id)).order_by(Category.name)
    )).scalars().all()
    return request.app.state.templates.TemplateResponse("categories/index.html", {"request": request, "user": user, "rows": rows, "error": None})

@router.get("/new", response_class=HTMLResponse)
async def new_form(request: Request, user=Depends(require_roles("Admin"))):
    return request.app.state.templates.TemplateResponse("categories/form.html", {"request": request, "user": user, "row": None, "error": None})

@router.post("/new")
async def create(request: Request, name: str = Form(...), db: AsyncSession = Depends(get_db), user=Depends(require_roles("Admin"))):
    c = Category(org_id=uuid.UUID(user.org_id), name=name.strip())
    db.add(c)
    await db.commit()
    await log_audit(db, user.org_id, user.id, "CREATE", "category", str(c.id), {"name": c.name})
    await db.commit()
    return r("/categories")

@router.get("/{category_id}/edit", response_class=HTMLResponse)
async def edit_form(category_id: str, request: Request, db: AsyncSession = Depends(get_db), user=Depends(require_roles("Admin"))):
    row = (await db.execute(select(Category).where(
        Category.id == uuid.UUID(category_id),
        Category.org_id == uuid.UUID(user.org_id),
    ))).scalar_one()
    return request.app.state.templates.TemplateResponse("categories/form.html", {"request": request, "user": user, "row": row, "error": None})

@router.post("/{category_id}/edit")
async def update(category_id: str, name: str = Form(...), db: AsyncSession = Depends(get_db), user=Depends(require_roles("Admin"))):
    row = (await db.execute(select(Category).where(
        Category.id == uuid.UUID(category_id),
        Category.org_id == uuid.UUID(user.org_id),
    ))).scalar_one()

    row.name = name.strip()
    await db.commit()

    await log_audit(db, user.org_id, user.id, "UPDATE", "category", category_id, {"name": row.name})
    await db.commit()
    return r("/categories")

@router.post("/{category_id}/delete")
async def delete(category_id: str, request: Request, db: AsyncSession = Depends(get_db), user=Depends(require_roles("Admin"))):
    # No permitir borrar si hay productos relacionados
    has_products = (await db.execute(select(
        exists().where(
            Product.org_id == uuid.UUID(user.org_id),
            Product.category_id == uuid.UUID(category_id)
        )
    ))).scalar()

    if has_products:
        rows = (await db.execute(select(Category).where(Category.org_id == uuid.UUID(user.org_id)).order_by(Category.name))).scalars().all()
        return request.app.state.templates.TemplateResponse(
            "categories/index.html",
            {"request": request, "user": user, "rows": rows, "error": "No puedes borrar: hay productos asociados a esta categoría."}
        )

    row = (await db.execute(select(Category).where(
        Category.id == uuid.UUID(category_id),
        Category.org_id == uuid.UUID(user.org_id),
    ))).scalar_one()

    await db.delete(row)
    await db.commit()

    await log_audit(db, user.org_id, user.id, "DELETE", "category", category_id, {"name": row.name})
    await db.commit()
    return r("/categories")
