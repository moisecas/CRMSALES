import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import Sale, SaleItem, Product, Customer
from app.services.sales import confirm_sale, cancel_sale

router = APIRouter(prefix="/sales")


def _u(x: str) -> uuid.UUID:
    return uuid.UUID(str(x))


def r(url: str):
    return RedirectResponse(url, status_code=302)


@router.get("", response_class=HTMLResponse)
async def sales_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    rows = (
        await db.execute(
            select(Sale)
            .where(Sale.org_id == _u(user.org_id))
            .order_by(Sale.created_at.desc())
        )
    ).scalars().all()

    return request.app.state.templates.TemplateResponse(
        "sales/index.html",
        {"request": request, "user": user, "rows": rows, "error": None},
    )


@router.post("/new")
async def sales_new(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("Admin", "Vendedor")),
):
    s = Sale(
        org_id=_u(user.org_id),
        customer_id=None,
        number=None,
        date=date.today(),
        status="DRAFT",
        total=Decimal("0"),
        created_by_user_id=_u(user.id) if getattr(user, "id", None) else None,
    )
    db.add(s)
    await db.commit()
    return r(f"/sales/{s.id}")


@router.get("/{sale_id}", response_class=HTMLResponse)
async def sales_detail(
    sale_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    err = request.query_params.get("err")

    sale = (
        await db.execute(
            select(Sale).where(
                Sale.id == _u(sale_id),
                Sale.org_id == _u(user.org_id),
            )
        )
    ).scalar_one()

    items = (
        await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))
    ).scalars().all()

    products = (
        await db.execute(
            select(Product)
            .where(
                Product.org_id == _u(user.org_id),
                Product.active == True,  # noqa: E712
            )
            .order_by(Product.name)
        )
    ).scalars().all()

    customers = (
        await db.execute(
            select(Customer)
            .where(Customer.org_id == _u(user.org_id))
            .order_by(Customer.name)
        )
    ).scalars().all()

    return request.app.state.templates.TemplateResponse(
        "sales/detail.html",
        {
            "request": request,
            "user": user,
            "sale": sale,
            "items": items,
            "products": products,
            "customers": customers,
            "error": err,
        },
    )


@router.post("/{sale_id}/set_customer")
async def set_customer(
    sale_id: str,
    customer_id: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("Admin", "Vendedor")),
):
    sale = (
        await db.execute(
            select(Sale).where(
                Sale.id == _u(sale_id),
                Sale.org_id == _u(user.org_id),
            )
        )
    ).scalar_one()

    if sale.status != "DRAFT":
        return r(f"/sales/{sale_id}")

    sale.customer_id = _u(customer_id) if customer_id else None
    await db.commit()
    return r(f"/sales/{sale_id}")


@router.post("/{sale_id}/items/add")
async def add_item(
    sale_id: str,
    product_id: str = Form(...),
    qty: int = Form(...),
    unit_price: Decimal = Form(None),
    discount: Decimal = Form(0),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("Admin", "Vendedor")),
):
    sale = (
        await db.execute(
            select(Sale).where(
                Sale.id == _u(sale_id),
                Sale.org_id == _u(user.org_id),
            )
        )
    ).scalar_one()

    if sale.status != "DRAFT":
        return r(f"/sales/{sale_id}")

    p = (
        await db.execute(
            select(Product).where(
                Product.id == _u(product_id),
                Product.org_id == _u(user.org_id),
            )
        )
    ).scalar_one()

    if qty <= 0:
        return r(f"/sales/{sale_id}?err=La+cantidad+debe+ser+mayor+a+0")

    # ✅ precio por defecto: el del producto si no viene en el form
    up = unit_price if unit_price is not None else Decimal(str(p.price or 0))

    # ✅ descuento opcional
    disc = discount if discount is not None else Decimal("0")

    line_total = (Decimal(str(up)) * Decimal(qty)) - Decimal(str(disc))
    if line_total < 0:
        line_total = Decimal("0")

    db.add(
        SaleItem(
            sale_id=sale.id,
            product_id=p.id,
            qty=qty,
            unit_price=up,
            discount=disc,
            line_total=line_total,
        )
    )
    await db.commit()
    return r(f"/sales/{sale_id}")


@router.post("/{sale_id}/items/{item_id}/delete")
async def delete_item(
    sale_id: str,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("Admin", "Vendedor")),
):
    sale = (
        await db.execute(
            select(Sale).where(
                Sale.id == _u(sale_id),
                Sale.org_id == _u(user.org_id),
            )
        )
    ).scalar_one()

    if sale.status != "DRAFT":
        return r(f"/sales/{sale_id}")

    it = (
        await db.execute(
            select(SaleItem).where(
                SaleItem.id == _u(item_id),
                SaleItem.sale_id == sale.id,
            )
        )
    ).scalar_one()

    await db.delete(it)
    await db.commit()
    return r(f"/sales/{sale_id}")


# ✅ IMPORTANTE: sin /sales acá, porque ya tienes prefix="/sales"
@router.post("/{sale_id}/confirm")
async def do_confirm(
    sale_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("Admin", "Vendedor")),
):
    try:
        await confirm_sale(db, sale_id=sale_id, org_id=user.org_id, actor_user_id=user.id)
    except ValueError as e:
        msg = str(e).replace(" ", "+")
        return RedirectResponse(f"/sales/{sale_id}?err={msg}", status_code=302)

    return RedirectResponse(f"/sales/{sale_id}", status_code=302)


@router.post("/{sale_id}/cancel")
async def do_cancel(
    sale_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("Admin")),
):
    try:
        await cancel_sale(db, sale_id=sale_id, org_id=user.org_id, actor_user_id=user.id)
    except ValueError as e:
        msg = str(e).replace(" ", "+")
        return RedirectResponse(f"/sales/{sale_id}?err={msg}", status_code=302)

    return r(f"/sales/{sale_id}")


@router.post("/{sale_id}/delete")
async def delete_sale(
    sale_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("Admin")),
):
    sale = (
        await db.execute(
            select(Sale).where(
                Sale.id == _u(sale_id),
                Sale.org_id == _u(user.org_id),
            )
        )
    ).scalar_one()

    if sale.status != "DRAFT":
        return r(f"/sales/{sale_id}?err=Solo+puedes+borrar+ventas+en+DRAFT")

    items = (
        await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))
    ).scalars().all()

    for it in items:
        await db.delete(it)

    await db.delete(sale)
    await db.commit()
    return r("/sales")
