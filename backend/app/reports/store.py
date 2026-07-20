"""File des jobs de rapport dans PostGIS (table report_jobs, spec §8).

L'API dépose (`creer`) et consulte (`lire`) ; le worker réclame (`reclamer`, avec
FOR UPDATE SKIP LOCKED pour autoriser plusieurs consommateurs), conclut et purge.
La table est créée à la volée : pas besoin de rejouer `ingest schema` sur une base
existante.
"""
import json
import uuid
from pathlib import Path

import asyncpg

from .. import config
from ..schemas import ReportRequest

DDL = """
CREATE TABLE IF NOT EXISTS report_jobs (
    id      uuid PRIMARY KEY,
    statut  text NOT NULL DEFAULT 'pending',
    demande jsonb NOT NULL,
    erreur  text,
    fichier text,
    cree    timestamptz NOT NULL DEFAULT now(),
    maj     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS report_jobs_statut_idx ON report_jobs (statut, cree);
"""


def chemin_pdf(fichier: str) -> Path:
    return Path(config.REPORTS_DIR) / fichier


async def _ensure(p: asyncpg.Pool) -> None:
    await p.execute(DDL)


async def creer(p: asyncpg.Pool, req: ReportRequest) -> str:
    await _ensure(p)
    job_id = str(uuid.uuid4())
    await p.execute(
        "INSERT INTO report_jobs (id, demande) VALUES ($1, $2::jsonb)",
        job_id, req.model_dump_json(),
    )
    return job_id


async def lire(p: asyncpg.Pool, job_id: str) -> asyncpg.Record | None:
    await _ensure(p)
    try:
        uuid.UUID(job_id)
    except ValueError:
        return None
    return await p.fetchrow("SELECT * FROM report_jobs WHERE id = $1", job_id)


async def reclamer(p: asyncpg.Pool) -> tuple[str, ReportRequest] | None:
    """Prend le plus ancien job en attente, le marque `running` (concurrence sûre)."""
    async with p.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """SELECT id, demande FROM report_jobs WHERE statut = 'pending'
               ORDER BY cree LIMIT 1 FOR UPDATE SKIP LOCKED"""
        )
        if row is None:
            return None
        await conn.execute(
            "UPDATE report_jobs SET statut = 'running', maj = now() WHERE id = $1", row["id"]
        )
        return str(row["id"]), ReportRequest(**json.loads(row["demande"]))


async def conclure(p: asyncpg.Pool, job_id: str, fichier: str | None, erreur: str | None = None) -> None:
    await p.execute(
        """UPDATE report_jobs SET statut = $2, fichier = $3, erreur = $4, maj = now()
           WHERE id = $1""",
        job_id, "error" if erreur else "done", fichier, erreur,
    )


async def purger(p: asyncpg.Pool) -> int:
    """Purge 24 h (spec §8) : fichiers PDF puis lignes. Retourne le nombre purgé."""
    await _ensure(p)
    rows = await p.fetch(
        "DELETE FROM report_jobs WHERE cree < now() - interval '%s hours' RETURNING fichier"
        % config.REPORT_RETENTION_H
    )
    for r in rows:
        if r["fichier"]:
            chemin_pdf(r["fichier"]).unlink(missing_ok=True)
    return len(rows)
