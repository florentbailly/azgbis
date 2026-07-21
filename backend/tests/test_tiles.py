"""Logique pure du tuilage : mailles par zoom, bornes z/x/y, variantes SQL."""
import pytest
from fastapi import HTTPException

from app import tiles


def test_niveau_par_zoom():
    assert tiles._niveau(5) == "departement"
    assert tiles._niveau(8) == "departement"
    assert tiles._niveau(9) == "commune"
    assert tiles._niveau(11) == "commune"
    assert tiles._niveau(12) == "section"
    assert tiles._niveau(13) == "section"
    assert tiles._niveau(14) == "parcelle"
    assert tiles._niveau(18) == "parcelle"


@pytest.mark.parametrize("z,x,y", [(0, 0, 0), (14, 8412, 5842), (22, 2**22 - 1, 0)])
def test_zxy_valides(z, x, y):
    tiles._check_zxy(z, x, y)  # ne lève pas


@pytest.mark.parametrize("z,x,y", [(-1, 0, 0), (23, 0, 0), (5, 32, 0), (5, 0, -1)])
def test_zxy_hors_bornes(z, x, y):
    with pytest.raises(HTTPException) as e:
        tiles._check_zxy(z, x, y)
    assert e.value.status_code == 400


def test_sql_periode_couvre_les_quatre_niveaux():
    assert set(tiles.SQL_PRIX_PERIODE) == {"parcelle", "section", "commune", "departement"}
    for sql in tiles.SQL_PRIX_PERIODE.values():
        assert "date_mutation BETWEEN $5 AND $6" in sql


def test_couches_classes_declarees():
    assert "radon" in tiles.CLASSES_COUCHES
