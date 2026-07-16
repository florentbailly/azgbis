"""Accès PostGIS optionnel : sans DATABASE_URL, les thèmes batch répondent « source non chargée »."""
import asyncpg

from . import config

_pool: asyncpg.Pool | None = None


async def pool() -> asyncpg.Pool | None:
    global _pool
    if not config.DATABASE_URL:
        return None
    if _pool is None:
        _pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5)
    return _pool


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


NO_DB_WARNING = (
    "Base PostGIS non configurée (DATABASE_URL absent) ou source non encore importée : "
    "lancer le pipeline d'ingestion (voir pipeline/README.md)."
)
