"""Résolution des zones : surfaces métriques, validation des entrées."""
import math

import pytest
from pydantic import ValidationError

from app.geo import resolve_zone
from app.schemas import ZoneInput


def test_point_rayons_surfaces():
    zone = resolve_zone(ZoneInput(type="point_radii", center=(4.83, 45.76),
                                  small_radius_m=500, large_radius_m=1500))
    # Buffer métrique en Lambert-93 : surface ≈ πr² (polygone approché, tolérance 2 %)
    assert zone.small_l93.area == pytest.approx(math.pi * 500**2, rel=0.02)
    assert zone.large_l93.area == pytest.approx(math.pi * 1500**2, rel=0.02)
    assert zone.resume["surface_zone_etude_m2"] < zone.resume["surface_zone_contexte_m2"]


def test_polygone_contexte_egale_etude():
    carre = {"type": "Polygon", "coordinates": [[[4.8, 45.7], [4.9, 45.7], [4.9, 45.8], [4.8, 45.8], [4.8, 45.7]]]}
    zone = resolve_zone(ZoneInput(type="polygon", geometry=carre))
    assert zone.small_l93.area == zone.large_l93.area
    assert zone.large_radius_m > 0


def test_polygon_sans_geometrie_refuse():
    with pytest.raises(ValidationError):
        ZoneInput(type="polygon")


def test_rayons_incoherents_refuses():
    with pytest.raises(ValidationError):
        ZoneInput(type="point_radii", center=(4.8, 45.7), small_radius_m=2000, large_radius_m=500)


def test_rayon_excessif_refuse():
    with pytest.raises(ValidationError):
        ZoneInput(type="point_radii", center=(4.8, 45.7), small_radius_m=500, large_radius_m=60_000)
