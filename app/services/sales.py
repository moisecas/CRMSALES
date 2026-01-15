# app/services/sales.py

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Sale, SaleItem, Product, StockMovement, Sequence
from app.services._tx import reset_tx_if_needed


def _u(x: str) -> uuid.UUID:
    return uuid.UUID(str(x))


async def _next_sale_number(db: AsyncSession, org_id: str) -> str:
    """
    Genera consecutivo por organización: V-000001, V-000002, ...
    Bloquea la fila de Sequence para evitar duplicados en concurrencia.
    """
    org_uuid = _u(org_id)

    q = (
        select(Sequence)
        .where(Sequence.org_id == org_uuid, Sequence.key == "SALE")
        .with_for_update()
    )

    seq = (await db.execute(q)).scalar_one_or_none()
    if not seq:
        seq = Sequence(org_id=org_uuid, key="SALE", current_value=0)
        db.add(seq)
        await db.flush()
        # Re-lee bloqueando
        seq = (await db.execute(q)).scalar_one()

    seq.current_value += 1
    await db.flush()

    return f"V-{seq.current_value:06d}"


async def confirm_sale(db: AsyncSession, sale_id: str, org_id: str, actor_user_id: str):
    """
    DRAFT -> CONFIRMED
    - Valida stock suficiente
    - Genera movimientos OUT
    - Descuenta stock
    - Calcula total
    Todo atómico.
    """
    await reset_tx_if_needed(db)

    org_uuid = _u(org_id)
    sale_uuid = _u(sale_id)

    async with db.begin():
        sale = (
            await db.execute(
                select(Sale)
                .where(Sale.id == sale_uuid, Sale.org_id == org_uuid)
                .with_for_update()
            )
        ).scalar_one()

        if sale.status != "DRAFT":
            raise ValueError("Solo se puede confirmar una venta en DRAFT.")

        items = (
            await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))
        ).scalars().all()

        if not items:
            raise ValueError("No puedes confirmar una venta sin items.")

        product_ids = [it.product_id for it in items]

        products = (
            await db.execute(
                select(Product)
                .where(
                    Product.org_id == org_uuid,
                    Product.id.in_(product_ids),
                )
                .with_for_update()
            )
        ).scalars().all()

        prod_map = {p.id: p for p in products}

        # Validar stock + productos válidos
        for it in items:
            p = prod_map.get(it.product_id)
            if not p:
                raise ValueError("Producto inválido o no pertenece a la organización.")
            if p.active is False:
                raise ValueError(f"El producto {p.sku} está inactivo.")
            if (p.current_stock or 0) < it.qty:
                raise ValueError(
                    f"Stock insuficiente para {p.sku} - {p.name} "
                    f"(disp: {p.current_stock}, req: {it.qty})"
                )

        # Asignar consecutivo
        if not sale.number:
            sale.number = await _next_sale_number(db, org_id)

        # Total + line totals
        total = Decimal("0")
        for it in items:
            unit = Decimal(str(it.unit_price or 0))
            disc = Decimal(str(it.discount or 0))
            line_total = (unit * Decimal(it.qty)) - disc
            if line_total < 0:
                line_total = Decimal("0")
            it.line_total = line_total
            total += line_total

        sale.total = total
        sale.status = "CONFIRMED"
        sale.date = sale.date or date.today()

        # Movimientos OUT + bajar stock
        for it in items:
            p = prod_map[it.product_id]
            p.current_stock = (p.current_stock or 0) - it.qty

            db.add(
                StockMovement(
                    org_id=org_uuid,
                    product_id=p.id,
                    type="OUT",
                    qty=it.qty,
                    ref_type="SALE",
                    ref_id=sale.id,
                    note=f"Venta {sale.number} (actor {actor_user_id})",
                )
            )

        await db.flush()


async def cancel_sale(db: AsyncSession, sale_id: str, org_id: str, actor_user_id: str):
    """
    CONFIRMED -> CANCELED
    - Crea movimientos IN (reverso)
    - Devuelve stock
    Todo atómico.
    """
    await reset_tx_if_needed(db)

    org_uuid = _u(org_id)
    sale_uuid = _u(sale_id)

    async with db.begin():
        sale = (
            await db.execute(
                select(Sale)
                .where(Sale.id == sale_uuid, Sale.org_id == org_uuid)
                .with_for_update()
            )
        ).scalar_one()

        if sale.status != "CONFIRMED":
            raise ValueError("Solo se puede cancelar una venta CONFIRMED.")

        items = (
            await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))
        ).scalars().all()

        if not items:
            # raro, pero por seguridad
            sale.status = "CANCELED"
            await db.flush()
            return

        product_ids = [it.product_id for it in items]

        products = (
            await db.execute(
                select(Product)
                .where(
                    Product.org_id == org_uuid,
                    Product.id.in_(product_ids),
                )
                .with_for_update()
            )
        ).scalars().all()

        prod_map = {p.id: p for p in products}

        # Movimientos IN + devolver stock
        for it in items:
            p = prod_map.get(it.product_id)
            if not p:
                raise ValueError("Producto inválido o no pertenece a la organización.")

            p.current_stock = (p.current_stock or 0) + it.qty

            db.add(
                StockMovement(
                    org_id=org_uuid,
                    product_id=p.id,
                    type="IN",
                    qty=it.qty,
                    ref_type="SALE_CANCEL",
                    ref_id=sale.id,
                    note=f"Cancelación venta {sale.number} (actor {actor_user_id})",
                )
            )

        sale.status = "CANCELED"
        await db.flush()
