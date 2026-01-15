import ssl
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from app.config import settings

def make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not settings.DB_SSL_VERIFY:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    poolclass=NullPool,  # PgBouncer ya hace pooling
    connect_args={
        "ssl": make_ssl_context(),
        "statement_cache_size": 0,  # <- clave para PgBouncer
    },
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
