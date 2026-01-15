import uuid
from datetime import date

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Product, Sale

router = APIRouter()

def _u(x: str) -> uuid.UUID:
    return uuid.UUID(x)

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    org = _u(user.org_id)

    total_products = (await db.execute(
        select(func.count(Product.id)).where(Product.org_id == org)
    )).scalar() or 0

    low_stock = (await db.execute(
        select(func.count(Product.id)).where(
            Product.org_id == org,
            Product.current_stock <= Product.stock_min
        )
    )).scalar() or 0

    # ventas del mes
    today = date.today()
    month_start = date(today.year, today.month, 1)

    sales_month = (await db.execute(
        select(func.coalesce(func.sum(Sale.total), 0)).where(
            Sale.org_id == org,
            Sale.status == "CONFIRMED",
            Sale.date >= month_start,
            Sale.date <= today,
        )
    )).scalar() or 0

    last_sales = (await db.execute(
        select(Sale).where(Sale.org_id == org).order_by(Sale.created_at.desc()).limit(10)
    )).scalars().all()

    low_products = (await db.execute(
        select(Product).where(
            Product.org_id == org,
            Product.current_stock <= Product.stock_min
        ).order_by(Product.current_stock.asc()).limit(10)
    )).scalars().all()

    return request.app.state.templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "total_products": total_products,
            "low_stock": low_stock,
            "sales_month": sales_month,
            "last_sales": last_sales,
            "low_products": low_products,
        },
    )
