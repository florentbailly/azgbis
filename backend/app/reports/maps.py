"""Cartes statiques du rapport (spec §8 ②).

Playwright/Chromium charge l'appli carto en mode « rendu » (`/?rendu=1&…`) : zone +
couches du thème + légende + échelle, puis capture le conteneur carte en PNG. Le rendu
papier est ainsi strictement identique au rendu écran — même code front, mêmes tuiles.
Une carte en échec ne bloque jamais le rapport : elle est remplacée par un avertissement.
"""
import json
import urllib.parse

from .. import catalog, config
from ..schemas import ZoneInput

VIEWPORT = {"width": 1160, "height": 780}  # ~ pleine largeur A4 à 150 dpi


def _url(zone: ZoneInput, couches: list[str]) -> str:
    zone_json = json.dumps(zone.model_dump(exclude_none=True), separators=(",", ":"))
    return (
        f"{config.RENDER_URL}/?rendu=1&couches={','.join(couches)}"
        f"&zone={urllib.parse.quote(zone_json)}"
    )


def couches_du_theme(theme: str) -> list[str]:
    for t in catalog.THEMES:
        if t["id"] == theme:
            return t.get("couches_rapport", [])
    return []


async def captures(zone: ZoneInput, themes: list[str]) -> tuple[dict[str, bytes], list[str]]:
    """PNG par section : clé `situation` (page de garde, zone seule) puis une par thème.

    Retourne aussi la liste des avertissements (cartes en échec).
    """
    from playwright.async_api import async_playwright

    images: dict[str, bytes] = {}
    avertissements: list[str] = []
    cibles = [("situation", [])] + [(t, couches_du_theme(t)) for t in themes]

    async with async_playwright() as pw:
        # --no-sandbox : Chromium tourne en root dans le conteneur worker, sans espace
        # de noms utilisateur — le sandbox refuserait de démarrer.
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        try:
            page = await browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
            for cle, couches in cibles:
                try:
                    await page.goto(_url(zone, couches), timeout=30_000)
                    # Le front pose #rendu-pret quand la carte est stable (tuiles chargées).
                    # state="attached" : le marqueur est un div vide, jamais « visible ».
                    await page.wait_for_selector("#rendu-pret", state="attached", timeout=60_000)
                    images[cle] = await page.locator("#map").screenshot(timeout=15_000)
                except Exception as e:  # une carte manquante ne doit pas tuer le rapport
                    avertissements.append(
                        f"Carte « {cle} » indisponible ({type(e).__name__}) : "
                        "le fond de carte ou une couche n'a pas répondu à temps."
                    )
        finally:
            await browser.close()
    return images, avertissements
