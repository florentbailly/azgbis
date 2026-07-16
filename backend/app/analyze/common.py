"""Outillage commun aux thèmes : exécution tolérante aux pannes d'une source."""
import datetime
from typing import Any, Awaitable, Callable

from ..clients.http import SourceError
from ..schemas import SourceRef, ThemeResult


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


async def collect(
    result: ThemeResult,
    label: str,
    coro: Awaitable[Any],
    on_ok: Callable[[Any], None],
) -> None:
    """Exécute un appel source ; en échec, ajoute un avertissement au lieu de propager (spec §7)."""
    try:
        on_ok(await coro)
    except SourceError as e:
        result.avertissements.append(f"{label} indisponible : {e}")
    except Exception as e:  # défaut de parsing d'une réponse inattendue
        result.avertissements.append(f"{label} : réponse inexploitable ({type(e).__name__}: {e})")


def source(result: ThemeResult, code: str, libelle: str, url: str, millesime: str | None = None) -> None:
    if not any(s.code == code for s in result.sources):
        result.sources.append(
            SourceRef(code=code, libelle=libelle, url=url, millesime=millesime or now_iso())
        )
