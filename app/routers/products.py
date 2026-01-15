import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, or_, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import Product, SaleItem, StockMovement  # 👈 StockMovement aquí

router = APIRouter(prefix="/products")


def _u(x: str) -> uuid.UUID:
    return uuid.UUID(x)


def r(url: str):
    return RedirectResponse(url, status_code=302)


@router.get("", response_class=HTMLResponse)
async def list_products(
    request: Request,
    q: str = "",
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    stmt = select(Product).where(Product.org_id == _u(user.org_id))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Product.sku.ilike(like), Product.name.ilike(like)))
    stmt = stmt.order_by(Product.created_at.desc())

    rows = (await db.execute(stmt)).scalars().all()
    return request.app.state.templates.TemplateResponse(
        "products/index.html",
        {"request": request, "user": user, "rows": rows, "q": q, "error": None},
    )


@router.get("/new", response_class=HTMLResponse)
async def new_form(request: Request, user=Depends(require_roles("Admin", "Bodeguero"))):
    return request.app.state.templates.TemplateResponse(
        "products/form.html",
        {"request": request, "user": user, "row": None, "error": None},
    )


@router.post("/new")
async def create(
    sku: str = Form(...),
    name: str = Form(...),
    category: str = Form(""),
    cost: Decimal = Form(0),
    price: Decimal = Form(0),
    stock_min: int = Form(0),
    active: bool = Form(True),
    initial_stock: int = Form(0),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("Admin", "Bodeguero")),
):
    initial_stock = int(initial_stock or 0)
    if initial_stock < 0:
        initial_stock = 0

    try:
        p = Product(
            org_id=_u(user.org_id),
            sku=sku.strip(),
            name=name.strip(),
            category=category.strip() or None,
            cost=cost,
            price=price,
            stock_min=stock_min,
            current_stock=initial_stock,
            active=bool(active),
            created_by_user_id=_u(user.id) if hasattr(Product, "created_by_user_id") else None,
        )
        db.add(p)
        await db.flush()  # ✅ para tener p.id sin commitear aún

        # ✅ Kardex (si tienes StockMovement)
        if initial_stock > 0:
            db.add(StockMovement(
                org_id=_u(user.org_id),
                product_id=p.id,
                type="IN",
                qty=initial_stock,
                ref_type="PRODUCT_INIT",
                ref_id=p.id,
                note=f"Stock inicial ({initial_stock})",
                actor_user_id=_u(user.id) if hasattr(StockMovement, "actor_user_id") else None,
            ))

        await db.commit()
        return r("/products")

    except Exception:
        await db.rollback()
        raise



@router.get("/{product_id}/edit", response_class=HTMLResponse)
async def edit_form(
    product_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("Admin", "Bodeguero")),
):
    row = (await db.execute(
        select(Product).where(
            Product.id == _u(product_id),
            Product.org_id == _u(user.org_id),
        )
    )).scalar_one()

    return request.app.state.templates.TemplateResponse(
        "products/form.html",
        {"request": request, "user": user, "row": row, "error": None},
    )


@router.post("/{product_id}/edit")
async def update(
    product_id: str,
    sku: str = Form(...),
    name: str = Form(...),
    category: str = Form(""),
    cost: Decimal = Form(0),
    price: Decimal = Form(0),
    stock_min: int = Form(0),
    active: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("Admin", "Bodeguero")),
):
    row = (await db.execute(
        select(Product).where(
            Product.id == _u(product_id),
            Product.org_id == _u(user.org_id),
        )
    )).scalar_one()

    row.sku = sku.strip()
    row.name = name.strip()
    row.category = category.strip() or None
    row.cost = cost
    row.price = price
    row.stock_min = stock_min
    row.active = bool(active)

    if hasattr(row, "updated_by_user_id"):
        row.updated_by_user_id = _u(user.id)
    if hasattr(row, "updated_at"):
        row.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return r("/products")


@router.post("/{product_id}/delete")
async def delete(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("Admin")),
):
    row = (await db.execute(
        select(Product).where(
            Product.id == _u(product_id),
            Product.org_id == _u(user.org_id),
        )
    )).scalar_one()

    has_sales = (await db.execute(
        select(exists().where(SaleItem.product_id == row.id))
    )).scalar()

    if has_sales:
        return RedirectResponse(url="/products?modal=cannot_delete&reason=sale", status_code=302)

    await db.delete(row)
    await db.commit()

