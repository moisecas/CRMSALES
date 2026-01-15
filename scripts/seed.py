import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.security import hash_password
from app.models import Organization, User, Product, Supplier, Customer, Sequence



def _connect_args():
    # Usa las mismas reglas de SSL que tu engine (con el toggle)
    # y el fix de PgBouncer para Supabase pooler.
    import ssl
    ctx = ssl.create_default_context()
    if not settings.DB_SSL_VERIFY:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return {"ssl": ctx, "statement_cache_size": 0}


async def main():
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        poolclass=NullPool,
        connect_args=_connect_args(),
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        async with db.begin():
            # ORG
            org = Organization(name="Tienda Demo COP")
            db.add(org)
            await db.flush()  # para tener org.id

            # USERS
            admin = User(
                org_id=org.id,
                role="Admin",
                name="Admin",
                email="admin@demo.com",
                password_hash=hash_password("Admin1234!"),
            )
            vendedor = User(
                org_id=org.id,
                role="Vendedor",
                name="Vendedor",
                email="vendedor@demo.com",
                password_hash=hash_password("Vendedor1234!"),
            )
            bodeguero = User(
                org_id=org.id,
                role="Bodeguero",
                name="Bodeguero",
                email="bodeguero@demo.com",
                password_hash=hash_password("Bodeguero1234!"),
            )
            db.add_all([admin, vendedor, bodeguero])

            # SEQUENCES
            db.add_all([
                Sequence(org_id=org.id, key="PURCHASE", current_value=0),
                Sequence(org_id=org.id, key="SALE", current_value=0),
            ])

            # SUPPLIERS
            db.add_all([
                Supplier(org_id=org.id, name="Proveedor A", phone="3000000001", email="prova@demo.com", notes=""),
                Supplier(org_id=org.id, name="Proveedor B", phone="3000000002", email="provb@demo.com", notes=""),
            ])

            # CUSTOMERS
            db.add_all([
                Customer(org_id=org.id, name="Cliente A", phone="3100000001", email="clia@demo.com", notes=""),
                Customer(org_id=org.id, name="Cliente B", phone="3100000002", email="clib@demo.com", notes=""),
            ])

            # PRODUCTS (10)
            products = []
            for i in range(1, 11):
                products.append(Product(
                    org_id=org.id,
                    sku=f"SKU-{i:03d}",
                    name=f"Producto {i}",
                    category="General",
                    cost=10000 + i * 500,
                    price=15000 + i * 700,
                    stock_min=5,
                    current_stock=20,
                    active=True,
                ))
            db.add_all(products)

    await engine.dispose()
    print("Seed OK ✅")
    print("Login admin: admin@demo.com / Admin1234!")


if __name__ == "__main__":
    asyncio.run(main())
