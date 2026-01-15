from sqlalchemy.ext.asyncio import AsyncSession

async def reset_tx_if_needed(db: AsyncSession) -> None:
    """
    SQLAlchemy 2.0 abre una tx automáticamente con el primer SELECT (autobegin).
    Si ya hay tx abierta (por dependencias u otras lecturas), la cerramos con rollback
    antes de iniciar una transacción atómica con db.begin().
    """
    if db.in_transaction():
        await db.rollback()
