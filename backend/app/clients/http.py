"""Client HTTP partagé : timeout unique, erreurs converties en avertissements côté appelant."""
import os
import ssl

import httpx

from .. import config


class SourceError(Exception):
    """Échec d'appel d'une source externe — à convertir en avertissement, jamais en 500."""


_client: httpx.AsyncClient | None = None


def _ssl_context() -> ssl.SSLContext | bool:
    """Contexte TLS : magasin de certificats système (proxys d'inspection d'entreprise),
    avec repli SSL_NO_VERIFY=1 pour les postes de dev dont le proxy bloque la révocation."""
    if os.environ.get("SSL_NO_VERIFY") == "1":
        return False
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return True  # défaut httpx (certifi)


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=config.SOURCE_TIMEOUT_S,
            verify=_ssl_context(),
            headers={"User-Agent": "azgbis/0.1 (outil interne de qualification de zone)"},
        )
    return _client


async def get_json(url: str, params: dict | None = None) -> dict | list:
    try:
        r = await client().get(url, params=params)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        raise SourceError(f"{url} → HTTP {e.response.status_code}") from e
    except httpx.HTTPError as e:
        raise SourceError(f"{url} → {type(e).__name__}: {e}") from e


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
