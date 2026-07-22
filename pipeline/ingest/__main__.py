"""CLI du pipeline batch (spec §9).

  python -m ingest schema                                 # crée les tables PostGIS
  python -m ingest dvf --dept 69 --years 2020-2024        # DVF géolocalisé d'un département
  python -m ingest contours --dept 69                     # contours cadastraux + carte des prix
  python -m ingest inpn --famille natura2000              # zonages INPN (WFS PatriNat)
  python -m ingest bati --dept 69                         # bâtiments BD TOPO (usage)
  python -m ingest sirene                                 # établissements actifs (NAF)
  python -m ingest enrich                                 # typologie des locaux (spec §5)
  python -m ingest status                                 # millésimes chargés
"""
import argparse
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(prog="ingest")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("schema")
    sub.add_parser("status")

    p_dvf = sub.add_parser("dvf")
    p_dvf.add_argument("--dept", required=True, help="code département, ex. 69 ou 2A")
    p_dvf.add_argument("--years", default="2021-2025", help="ex. 2021-2025 ou 2024 (le « latest » geo-dvf ne garde que 5 ans)")

    p_ctr = sub.add_parser("contours")
    p_ctr.add_argument("--dept", required=True,
                       help="département dont importer les contours cadastraux (après `ingest dvf`)")

    sub.add_parser("admin", help="contours administratifs France (communes + départements)")
    sub.add_parser("radon", help="potentiel radon par commune (après `ingest admin`)")

    p_bati = sub.add_parser("bati", help="bâtiments BD TOPO du département (usage_1/usage_2)")
    p_bati.add_argument("--dept", required=True, help="code département, ex. 69 ou 2A")

    p_sir = sub.add_parser("sirene", help="établissements SIRENE actifs des départements DVF")
    p_sir.add_argument("--dept", action="append",
                       help="restreindre à ce département (répétable ; défaut : ceux du DVF)")

    sub.add_parser("enrich", help="typologie des locaux DVF (après bati + sirene + contours)")

    p_inpn = sub.add_parser("inpn")
    p_inpn.add_argument("--famille", required=True, help="znieff1 | znieff2 | natura2000 | espace_protege | patrimoine_geol")
    p_inpn.add_argument("--file", help="repli hors ligne : archive shapefile/GPKG locale (défaut : WFS PatriNat)")
    p_inpn.add_argument("--territoire", default="METROP",
                        help="filtre territorial du WFS (défaut METROP ; ALL pour tout importer)")

    args = p.parse_args()

    if args.cmd == "schema":
        from .common import db

        sql = (Path(__file__).parents[1] / "schema.sql").read_text(encoding="utf-8")
        with db() as conn:
            conn.execute(sql)
            conn.commit()
        print("Schéma créé/à jour.")

    elif args.cmd == "status":
        from .common import db

        with db() as conn, conn.cursor() as cur:
            cur.execute("SELECT code, millesime, date_import FROM sources ORDER BY date_import DESC LIMIT 30")
            for code, mil, dt in cur.fetchall():
                print(f"  {code:<24} {mil:<12} {dt:%Y-%m-%d %H:%M}")

    elif args.cmd == "dvf":
        from . import dvf

        if "-" in args.years:
            a, b = args.years.split("-")
            years = list(range(int(a), int(b) + 1))
        else:
            years = [int(args.years)]
        dvf.run(args.dept, years)

    elif args.cmd == "contours":
        from . import contours

        contours.run(args.dept)

    elif args.cmd == "admin":
        from . import admin

        admin.run()

    elif args.cmd == "radon":
        from . import radon

        radon.run()

    elif args.cmd == "bati":
        from . import bati

        bati.run(args.dept)

    elif args.cmd == "sirene":
        from . import sirene

        sirene.run(args.dept)

    elif args.cmd == "enrich":
        from . import enrich

        enrich.run()

    elif args.cmd == "inpn":
        from . import inpn

        inpn.run(args.famille, args.file, None if args.territoire == "ALL" else args.territoire)


if __name__ == "__main__":
    main()
