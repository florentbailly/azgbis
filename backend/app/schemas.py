from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, model_validator

Theme = Literal[
    "risques_naturels",
    "risques_technologiques",
    "environnement",
    "urbanisme",
    "marche_ventes",
]


class ZoneInput(BaseModel):
    """Zone d'étude : polygone GeoJSON, ou point + petit/grand rayon (spec §4)."""

    type: Literal["polygon", "point_radii"]
    geometry: Optional[dict[str, Any]] = None  # GeoJSON Polygon (WGS84)
    center: Optional[tuple[float, float]] = None  # [lon, lat]
    small_radius_m: Optional[float] = Field(None, gt=0, le=50_000)
    large_radius_m: Optional[float] = Field(None, gt=0, le=50_000)

    @model_validator(mode="after")
    def _check(self) -> "ZoneInput":
        if self.type == "polygon" and not self.geometry:
            raise ValueError("zone.geometry requis pour type=polygon")
        if self.type == "point_radii":
            if self.center is None or self.small_radius_m is None or self.large_radius_m is None:
                raise ValueError("center, small_radius_m et large_radius_m requis pour type=point_radii")
            if self.large_radius_m < self.small_radius_m:
                raise ValueError("large_radius_m doit être >= small_radius_m")
        return self


class AnalyzeRequest(BaseModel):
    zone: ZoneInput
    themes: list[Theme]


class ExportRequest(BaseModel):
    """Corps de POST /dvf/export.xlsx : la zone seule (le thème est implicite)."""

    zone: ZoneInput


class SourceRef(BaseModel):
    code: str
    libelle: str
    url: str
    millesime: Optional[str] = None  # millésime batch, ou date/heure d'appel API live


class ThemeResult(BaseModel):
    theme: str
    indicateurs: dict[str, Any] = {}
    items: list[dict[str, Any]] = []
    avertissements: list[str] = []
    sources: list[SourceRef] = []


class AnalyzeResponse(BaseModel):
    zone_resume: dict[str, Any]
    resultats: list[ThemeResult]


class ReportRequest(AnalyzeRequest):
    """Corps de POST /reports (spec §7) : celui d'analyze + les champs de page de garde."""

    client_ref: str = ""
    titre: str = ""
    auteur: str = ""
