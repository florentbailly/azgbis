"""Géométries de zone : normalisation WGS84, buffers métriques, résumé."""
from dataclasses import dataclass

from pyproj import Transformer
from shapely.geometry import Point, shape, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform

from .schemas import ZoneInput

_TO_L93 = Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True).transform
_TO_WGS84 = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True).transform


@dataclass
class Zone:
    """Zone résolue : `small` = zone d'étude, `large` = zone de contexte/comparables (spec §4)."""

    small_wgs84: BaseGeometry
    large_wgs84: BaseGeometry
    small_l93: BaseGeometry
    large_l93: BaseGeometry
    centroid_lonlat: tuple[float, float]
    # rayon englobant de chaque emprise, borné pour les APIs qui attendent latlon+rayon
    small_radius_m: float
    large_radius_m: float

    @property
    def resume(self) -> dict:
        return {
            "surface_zone_etude_m2": round(self.small_l93.area),
            "surface_zone_contexte_m2": round(self.large_l93.area),
            "centre": list(self.centroid_lonlat),
            "rayon_englobant_m": round(self.large_radius_m),
            "geometrie_zone_etude": mapping(self.small_wgs84),
        }


def resolve_zone(z: ZoneInput) -> Zone:
    if z.type == "point_radii":
        lon, lat = z.center  # type: ignore[misc]
        center_l93 = shp_transform(_TO_L93, Point(lon, lat))
        small_l93 = center_l93.buffer(z.small_radius_m)  # type: ignore[arg-type]
        large_l93 = center_l93.buffer(z.large_radius_m)  # type: ignore[arg-type]
        return Zone(
            small_wgs84=shp_transform(_TO_WGS84, small_l93),
            large_wgs84=shp_transform(_TO_WGS84, large_l93),
            small_l93=small_l93,
            large_l93=large_l93,
            centroid_lonlat=(lon, lat),
            small_radius_m=float(z.small_radius_m),  # type: ignore[arg-type]
            large_radius_m=float(z.large_radius_m),  # type: ignore[arg-type]
        )

    geom_wgs84 = shape(z.geometry)  # type: ignore[arg-type]
    if not geom_wgs84.is_valid:
        geom_wgs84 = geom_wgs84.buffer(0)
    geom_l93 = shp_transform(_TO_L93, geom_wgs84)
    centroid_l93 = geom_l93.centroid
    radius = max(centroid_l93.distance(Point(c)) for c in geom_l93.exterior.coords)
    centroid_wgs84 = shp_transform(_TO_WGS84, centroid_l93)
    return Zone(
        small_wgs84=geom_wgs84,
        large_wgs84=geom_wgs84,
        small_l93=geom_l93,
        large_l93=geom_l93,
        centroid_lonlat=(centroid_wgs84.x, centroid_wgs84.y),
        small_radius_m=radius,
        large_radius_m=radius,
    )


def geojson_param(geom_wgs84: BaseGeometry, max_chars: int = 8000) -> tuple[str, bool]:
    """Sérialise une géométrie pour un paramètre d'URL (API Carto).

    Simplifie progressivement si trop longue ; en dernier recours l'enveloppe est utilisée.
    Retourne (chaîne, True si la géométrie a dû être dégradée) — T-04 de la spec.
    """
    import json

    simplified = False
    g = geom_wgs84
    for tol in (0.0, 0.0001, 0.0005, 0.002):
        if tol:
            g = geom_wgs84.simplify(tol, preserve_topology=True)
            simplified = True
        s = json.dumps(mapping(g), separators=(",", ":"))
        if len(s) <= max_chars:
            return s, simplified
    return json.dumps(mapping(geom_wgs84.envelope), separators=(",", ":")), True
