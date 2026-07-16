"""Outillage commun du pipeline : connexion PostGIS, traçabilité `sources`, téléchargements."""
import hashlib
import os
import ssl
from pathlib import Path

import httpx
import psycopg

RAW_DIR = Path(os.environ.get("PIPELINE_RAW_DIR", Path(__file__).resolve().parents[1] / "raw"))


def db() -> psycopg.Connection:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit(
            "DATABASE_URL manquant. Exemple :\n"
            "  $env:DATABASE_URL = 'postgresql://azgbis:azgbis@localhost:5432/azgbis'"
        )
    return psycopg.connect(url)


def register_source(conn: psycopg.Connection, code: str, libelle: str, url: str,
                    millesime: str, licence: str = "Licence Ouverte 2.0",
                    checksum: str | None = None) -> int:
    """Chaque import crée une ligne `sources` : c'est la base de la page de traçabilité du rapport."""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO sources (code, libelle, url_source, licence, millesime, checksum)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (code, libelle, url, licence, millesime, checksum),
        )
        return cur.fetchone()[0]


def ssl_context() -> ssl.SSLContext | bool:
    if os.environ.get("SSL_NO_VERIFY") == "1":
        return False
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return True


def download(url: str, dest_name: str) -> Path:
    """Télécharge dans pipeline/raw/ (conservation du brut daté, spec §9). Idempotent."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / dest_name
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  déjà présent : {dest}")
        return dest
    print(f"  téléchargement {url}")
    with httpx.stream("GET", url, verify=ssl_context(), timeout=600, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    print(f"  -> {dest} ({dest.stat().st_size / 1e6:.1f} Mo)")
    return dest


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
