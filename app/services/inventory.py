import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product, StockMovement


def _u(x: str) -> uuid.UUID:
    return uuid.UUID(x)


async def adjust_stock(
    db: AsyncSession,
    org_id: str,
    actor_user_id: str | None,
    product_id: str,
    qty: int,
    note: str = "",
):
    if qty == 0:
        raise ValueError("El ajuste no puede ser 0.")

    async with db.begin():
        p = (await db.execute(
            select(Product).where(
                Product.id == _u(product_id),
                Product.org_id == _u(org_id),
                Product.active == True,  # noqa: E712
            ).with_for_update()
        )).scalar_one()

        new_stock = (p.current_stock or 0) + qty
        if new_stock < 0:
            raise ValueError(f"Stock insuficiente. Stock actual: {p.current_stock}, ajuste: {qty}")

        p.current_stock = new_stock

        kwargs = {}
        # actor_user_id es opcional (depende si ya lo agregaste al modelo)
        if hasattr(StockMovement, "actor_user_id") and actor_user_id:
            kwargs["actor_user_id"] = _u(actor_user_id)

        db.add(StockMovement(
            org_id=_u(org_id),
            product_id=p.id,
            type="ADJUST",
            qty=qty,
            ref_type="adjust",
            ref_id=p.id,  # referencia simple
            note=note.strip() if note else "",
            **kwargs,
        ))
