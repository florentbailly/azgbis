"""Worker de rapports (spec §8) : `python -m app.reports.worker`.

Consomme la table report_jobs (2 jobs concurrents — suffisant pour ~100 rapports/mois,
objectif < 3 min par rapport) : ① analyse (même code que /zones/analyze) → ② cartes
statiques Playwright → ③ gabarit + WeasyPrint → PDF dans le volume partagé.
Purge les rapports de plus de 24 h toutes les 15 minutes.
"""
import asyncio
import traceback
from pathlib import Path

from .. import config, db
from ..analysis import run_analysis
from ..schemas import AnalyzeRequest, ReportRequest
from . import maps, render, store

CONCURRENCE = 2
SCRUTATION_S = 2
PURGE_S = 900


async def _traiter(job_id: str, demande: ReportRequest) -> str:
    analyse = await run_analysis(AnalyzeRequest(zone=demande.zone, themes=demande.themes))
    images, avert_cartes = await maps.captures(demande.zone, list(demande.themes))
    html = render.html_rapport(demande, analyse, images, avert_cartes)
    pdf = await asyncio.to_thread(render.pdf, html)  # WeasyPrint est bloquant

    fichier = f"rapport-{job_id}.pdf"
    dossier = Path(config.REPORTS_DIR)
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / fichier).write_bytes(pdf)
    return fichier


async def _consommateur(pool, num: int) -> None:
    while True:
        job = await store.reclamer(pool)
        if job is None:
            await asyncio.sleep(SCRUTATION_S)
            continue
        job_id, demande = job
        print(f"[worker {num}] rapport {job_id} : démarrage ({', '.join(demande.themes)})", flush=True)
        try:
            fichier = await _traiter(job_id, demande)
            await store.conclure(pool, job_id, fichier)
            print(f"[worker {num}] rapport {job_id} : terminé -> {fichier}", flush=True)
        except Exception as e:
            traceback.print_exc()
            await store.conclure(pool, job_id, None, f"{type(e).__name__} : {e}")
            print(f"[worker {num}] rapport {job_id} : ÉCHEC ({e})", flush=True)


async def _purge(pool) -> None:
    while True:
        try:
            n = await store.purger(pool)
            if n:
                print(f"[purge] {n} rapport(s) de plus de {config.REPORT_RETENTION_H} h supprimé(s)", flush=True)
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(PURGE_S)


async def main() -> None:
    pool = await db.pool()
    if pool is None:
        raise SystemExit("DATABASE_URL manquant : le worker de rapports a besoin de la base.")
    # Au démarrage, requalifier les jobs `running` orphelins (worker redémarré en plein job).
    await pool.execute(store.DDL)
    await pool.execute("UPDATE report_jobs SET statut = 'pending' WHERE statut = 'running'")
    print(f"[worker] prêt — {CONCURRENCE} jobs concurrents, PDF dans {config.REPORTS_DIR}", flush=True)
    await asyncio.gather(*(_consommateur(pool, i + 1) for i in range(CONCURRENCE)), _purge(pool))


if __name__ == "__main__":
    asyncio.run(main())
