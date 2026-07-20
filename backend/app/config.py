import os

GEORISQUES_API = os.environ.get("GEORISQUES_API", "https://www.georisques.gouv.fr/api/v1")
APICARTO_API = os.environ.get("APICARTO_API", "https://apicarto.ign.fr/api")
GEO_API = os.environ.get("GEO_API", "https://geo.api.gouv.fr")
BAN_API = os.environ.get("BAN_API", "https://api-adresse.data.gouv.fr")

# Base PostGIS (facultative en dev : sans elle, les thèmes batch répondent "source non chargée")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Timeout par source externe (spec §7) : une source en échec produit un avertissement, jamais un blocage.
SOURCE_TIMEOUT_S = float(os.environ.get("SOURCE_TIMEOUT_S", "15"))

# Rapports PDF (spec §8) : volume temporaire partagé api (lecture) / worker (écriture),
# purgé après 24 h ; URL du front que Playwright charge pour les cartes statiques.
REPORTS_DIR = os.environ.get("REPORTS_DIR", "/reports")
RENDER_URL = os.environ.get("RENDER_URL", "http://web:80")
REPORT_RETENTION_H = 24

# Rayon maximal accepté par la plupart des endpoints Géorisques (10 km).
GEORISQUES_MAX_RADIUS_M = 10_000

APP_VERSION = "0.1.0"
