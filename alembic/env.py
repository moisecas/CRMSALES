import asyncio
from logging.config import fileConfig
from alembic import context

import ssl
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models import Base

config = context.config

if config.config_file_name:
    try:
        fileConfig(config.config_file_name)
    except Exception:
        pass

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not settings.DB_SSL_VERIFY:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def run_migrations_online():
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        poolclass=NullPool,  # PgBouncer ya hace pooling
        connect_args={
            "ssl": make_ssl_context(),
            "statement_cache_size": 0,  # <- clave para PgBouncer
        },
    )

    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
