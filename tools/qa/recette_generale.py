# Recette navigateur de l'application (voir tools/qa/README.md pour l'exécution).
#
# Couvre : fraîcheur des données, couche radon (choroplèthe classes + légende),
# couche prix + filtre de période, mode Parcelle → analyse → export Excel,
# repli de la barre d'outils, tiroirs mobiles. Sortie : JSON sur stdout,
# captures dans /tmp/qa. Code retour 1 si un contrôle échoue.
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://web:80")
AUTH_USER = os.environ.get("QA_AUTH_USER")  # pour la préprod (basic auth)
AUTH_PASS = os.environ.get("QA_AUTH_PASS")
OUT = "/tmp/qa"
os.makedirs(OUT, exist_ok=True)

resultats: dict = {}
erreurs_console: list[str] = []


def page_options() -> dict:
    opts: dict = {}
    if AUTH_USER and AUTH_PASS:
        opts["http_credentials"] = {"username": AUTH_USER, "password": AUTH_PASS}
    return opts


with sync_playwright() as pw:
    nav = pw.chromium.launch(args=["--no-sandbox"])
    ctx = nav.new_context(viewport={"width": 1280, "height": 800}, **page_options())
    page = ctx.new_page()
    page.on("console", lambda m: erreurs_console.append(m.text) if m.type == "error" else None)

    # --- Fraîcheur des données (panneau Couches) -------------------------------------
    page.goto(f"{BASE}/#13/45.757/4.832", wait_until="networkidle", timeout=60_000)
    page.click("summary:has-text('Fraîcheur des données')")
    page.wait_for_timeout(300)
    resultats["fraicheur_lignes"] = page.locator(".fraicheur table tbody tr").count()
    page.screenshot(path=f"{OUT}/1_fraicheur.png")

    # --- Radon : choroplèthe par classes à l'échelle France --------------------------
    page.goto(f"{BASE}/#5/46.6/2.5", wait_until="networkidle", timeout=60_000)
    debut = time.monotonic()
    page.click("label:has-text('Potentiel radon (communes)')")
    page.wait_for_load_state("networkidle", timeout=30_000)
    resultats["radon_charge_s"] = round(time.monotonic() - debut, 1)
    resultats["radon_legende_classes"] = page.locator(".legendes .prix-legende-ligne").count()
    # networkidle précède la fin du rendu MapLibre (décodage + peinture des tuiles) :
    # sans cette marge, la capture montre un fond de carte vide alors que tout va bien.
    page.wait_for_timeout(2500)
    page.screenshot(path=f"{OUT}/2_radon_france.png")
    page.goto(f"{BASE}/#11/45.76/4.83", wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(1500)
    page.screenshot(path=f"{OUT}/3_radon_communes.png")
    page.click("label:has-text('Potentiel radon (communes)')")

    # --- Prix au m² : légende + filtre de période ------------------------------------
    page.goto(f"{BASE}/#13/45.757/4.832", wait_until="networkidle", timeout=60_000)
    tuiles_dvf: list[str] = []
    page.on("request", lambda r: tuiles_dvf.append(r.url) if "/api/tiles/dvf/" in r.url else None)
    page.click("label:has-text('Prix au m² (ventes DVF)')")
    page.wait_for_selector(".prix-periode", timeout=15_000)
    page.wait_for_timeout(3000)
    tuiles_dvf.clear()
    page.fill(".prix-periode-ligne >> nth=0 >> input[type=date]", "2025-01-01")
    page.wait_for_timeout(1500)
    page.wait_for_load_state("networkidle")
    resultats["prix_tuiles_filtrees"] = sum("debut=2025-01-01" in u for u in tuiles_dvf)
    page.screenshot(path=f"{OUT}/4_prix_periode.png")
    page.click(".prix-periode-reset")
    # Filtre typologique (panneau Couches) : décocher une typologie doit recharger
    # les tuiles avec ?typologies=… (recalcul des médianes à la volée).
    resultats["typo_filtre_visible"] = page.locator(".typo-filtre").is_visible()
    tuiles_dvf.clear()
    page.click("label[for='typo-residentiel']")
    page.wait_for_timeout(1500)
    page.wait_for_load_state("networkidle")
    resultats["typo_tuiles_filtrees"] = sum("typologies=" in u for u in tuiles_dvf)
    page.click("label[for='typo-residentiel']")  # tout réactiver avant la suite
    page.click("label:has-text('Prix au m² (ventes DVF)')")

    # --- Mode Parcelle : sélection → analyse → export Excel --------------------------
    page.click("button:has-text('Parcelle')")
    bouton = page.locator("button:has-text('Analyser la zone')")
    resultats["parcelle_bouton_grise_avant"] = bouton.is_disabled()
    page.mouse.click(640, 400)
    page.wait_for_selector(".result-theme:has-text('Parcelle sélectionnée')", timeout=30_000)
    page.wait_for_timeout(500)
    resultats["parcelle_bouton_actif_apres"] = bouton.is_enabled()
    if bouton.is_enabled():
        bouton.click()
        page.wait_for_selector(".zone-resume", timeout=120_000)
        # Typologies : libellés métier à l'écran, jamais les codes bruts (spec §5).
        resultats["typologie_codes_bruts"] = page.get_by_text("tertiaire_non_qualifie").count()
        export = page.locator("button:has-text('Télécharger les transactions (Excel)')")
        export.scroll_into_view_if_needed()
        resultats["export_bouton_visible"] = export.is_visible()
        with page.expect_download(timeout=60_000) as dl:
            export.click()
        fichier = f"{OUT}/transactions.xlsx"
        dl.value.save_as(fichier)
        resultats["export_octets"] = os.path.getsize(fichier)
        page.screenshot(path=f"{OUT}/5_analyse_parcelle.png")

    # --- Repli de la barre d'outils --------------------------------------------------
    page.click(".toolbar-plier")
    page.wait_for_timeout(200)
    resultats["toolbar_repliee"] = page.locator(".toolbar-repliee").is_visible()
    page.click(".toolbar-repliee button")
    page.close()

    # --- Mobile : tiroirs ------------------------------------------------------------
    mctx = nav.new_context(viewport={"width": 390, "height": 844}, has_touch=True,
                           is_mobile=True, **page_options())
    mob = mctx.new_page()
    mob.goto(f"{BASE}/#13/45.757/4.832", wait_until="networkidle", timeout=60_000)
    resultats["mobile_panneaux_fermes"] = mob.locator(".panel").count() == 0
    mob.click(".panel-toggle.left")
    mob.wait_for_timeout(400)
    resultats["mobile_tiroir_ouvert"] = mob.locator(".panel-left").is_visible()
    mob.click(".panel-left .panel-close")
    mob.wait_for_timeout(400)
    resultats["mobile_tiroir_referme"] = mob.locator(".panel-left").count() == 0
    mob.screenshot(path=f"{OUT}/6_mobile.png")
    mob.close()
    nav.close()

resultats["erreurs_console"] = erreurs_console[:10]

ATTENDUS = {
    "fraicheur_lignes": lambda v: v >= 1,
    "radon_legende_classes": lambda v: v == 3,
    "radon_charge_s": lambda v: v < 15,
    "prix_tuiles_filtrees": lambda v: v >= 1,
    "typo_filtre_visible": lambda v: v is True,
    "typo_tuiles_filtrees": lambda v: v >= 1,
    "parcelle_bouton_grise_avant": lambda v: v is True,
    "parcelle_bouton_actif_apres": lambda v: v is True,
    "typologie_codes_bruts": lambda v: v == 0,
    "export_bouton_visible": lambda v: v is True,
    "export_octets": lambda v: v > 5000,
    "toolbar_repliee": lambda v: v is True,
    "mobile_panneaux_fermes": lambda v: v is True,
    "mobile_tiroir_ouvert": lambda v: v is True,
    "mobile_tiroir_referme": lambda v: v is True,
    "erreurs_console": lambda v: v == [],
}
echecs = [k for k, ok in ATTENDUS.items() if k not in resultats or not ok(resultats[k])]
resultats["echecs"] = echecs
print(json.dumps(resultats, ensure_ascii=False, indent=2))
sys.exit(1 if echecs else 0)
