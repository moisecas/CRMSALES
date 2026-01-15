import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote_plus

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import Product, StockMovement
from app.services.inventory import adjust_stock

router = APIRouter(prefix="/inventory")


def _u(x: str) -> uuid.UUID:
    return uuid.UUID(x)


def r(url: str):
    return RedirectResponse(url, status_code=302)


@router.get("/stock", response_class=HTMLResponse)
async def stock_view(
    request: Request,
    q: str = "",
    low: int = 0,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    stmt = select(Product).where(Product.org_id == _u(user.org_id))

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Product.sku.ilike(like), Product.name.ilike(like)))

    if low:
        stmt = stmt.where(Product.current_stock <= Product.stock_min)

    stmt = stmt.order_by(Product.name)

    rows = (await db.execute(stmt)).scalars().all()

    return request.app.state.templates.TemplateResponse(
        "inventory/stock.html",
        {"request": request, "user": user, "rows": rows, "q": q, "low": low},
    )


@router.get("/kardex", response_class=HTMLResponse)
async def kardex_view(
    request: Request,
    product_id: str = "",
    mov_type: str = "",
    date_from: str = "",
    date_to: str = "",
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    # products para el filtro dropdown
    products = (await db.execute(
        select(Product)
        .where(Product.org_id == _u(user.org_id), Product.active == True)  # noqa: E712
        .order_by(Product.name)
    )).scalars().all()

    stmt = (
        select(StockMovement, Product)
        .join(Product, StockMovement.product_id == Product.id)
        .where(
            StockMovement.org_id == _u(user.org_id),
            Product.org_id == _u(user.org_id),
        )
    )

    if product_id:
        stmt = stmt.where(StockMovement.product_id == _u(product_id))

    if mov_type:
        stmt = stmt.where(StockMovement.type == mov_type)

    # filtros de fecha (timestamptz). parse simple YYYY-MM-DD
    def parse_d(s: str):
        return datetime.fromisoformat(s)  # "YYYY-MM-DD"

    if date_from:
        stmt = stmt.where(StockMovement.created_at >= parse_d(date_from))

    if date_to:
        # incluir todo el día: < (día siguiente a 00:00)
        dt_to = parse_d(date_to).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        stmt = stmt.where(StockMovement.created_at < dt_to)

    stmt = stmt.order_by(StockMovement.created_at.desc()).limit(500)

    rows = (await db.execute(stmt)).all()  # lista de (StockMovement, Product)

    return request.app.state.templates.TemplateResponse(
        "inventory/kardex.html",
        {
            "request": request,
            "user": user,
            "rows": rows,
            "products": products,
            "product_id": product_id,
            "mov_type": mov_type,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@router.get("/adjust", response_class=HTMLResponse)
async def adjust_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("Admin", "Bodeguero")),
):
    # ✅ mensajes por querystring (evita render con ORM expirado tras rollback)
    ok = request.query_params.get("ok")
    err = request.query_params.get("err")

    products = (await db.execute(
        select(Product)
        .where(Product.org_id == _u(user.org_id), Product.active == True)  # noqa: E712
        .order_by(Product.name)
    )).scalars().all()

    return request.app.state.templates.TemplateResponse(
        "inventory/adjust.html",
        {"request": request, "user": user, "products": products, "error": err, "ok": ok},
    )


@router.post("/adjust")
async def adjust_submit(
    request: Request,
    product_id: str = Form(...),
    qty: int = Form(...),  # permite negativos
    note: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("Admin", "Bodeguero")),
):
    try:
        await adjust_stock(
            db,
            org_id=user.org_id,
            actor_user_id=user.id,
            product_id=product_id,
            qty=qty,
            note=note,
        )
        # ✅ PRG: Post -> Redirect -> Get
        return r("/inventory/adjust?ok=" + quote_plus("Ajuste aplicado ✅"))

    except Exception as e:
        await db.rollback()
        return r("/inventory/adjust?err=" + quote_plus(str(e)))
