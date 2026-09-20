"""
Construit les fichiers de données affichés par l'application :
  - data/quartiers.geojson  : contours des quartiers d'Orléans (Orléans Métropole, open data)
  - data/ventes.json        : ventes immobilières géolocalisées sur la dernière année disponible (DVF, data.gouv.fr)
  - data/meta.json          : informations sur la fraîcheur des données (dates, nombre de ventes, etc.)

Pourquoi une "dernière année disponible" et pas "les 12 derniers mois" au sens strict ?
La donnée officielle DVF a un délai de publication de 6 à 18 mois (le temps que le
notariat/le fisc traitent chaque vente). On prend donc les 365 jours les plus récents
PARMI ce qui est publié, et on affiche clairement la période couverte dans l'appli.

Ce script est fait pour être lancé par la GitHub Action (.github/workflows/update-data.yml),
qui tourne sur des serveurs ayant un accès internet normal.
"""

from __future__ import annotations

import gzip
import io
import json
import sys
from datetime import date, timedelta

import pandas as pd
import requests
from shapely.geometry import Point, shape

# --- Paramètres du projet -----------------------------------------------

INSEE_COMMUNE = "45234"  # Code INSEE de la commune d'Orléans
DEPARTEMENT = "45"  # Loiret

QUARTIERS_DATASET = "administratif_adm_quartier"
QUARTIERS_URLS = [
    f"https://data.orleans-metropole.fr/api/explore/v2.1/catalog/datasets/{QUARTIERS_DATASET}/exports/geojson",
    f"https://data.orleans-metropole.fr/explore/dataset/{QUARTIERS_DATASET}/download/?format=geojson&timezone=Europe/Paris",
]

TYPES_LOCAUX_RETENUS = {"Maison", "Appartement"}

OUT_DIR = "data"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --- 1. Contours des quartiers -------------------------------------------


def fetch_quartiers() -> dict:
    last_error = None
    for url in QUARTIERS_URLS:
        try:
            log(f"Téléchargement des quartiers depuis {url} ...")
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            geojson = r.json()
            if geojson.get("features"):
                log(f"  -> {len(geojson['features'])} quartiers récupérés.")
                return geojson
        except Exception as e:  # noqa: BLE001
            last_error = e
            log(f"  échec : {e}")
    raise RuntimeError(f"Impossible de récupérer les quartiers d'Orléans : {last_error}")


def quartier_name(props: dict) -> str:
    for key in ("nom", "libelle", "lib_quartier", "quartier", "name", "nom_quartier"):
        if key in props and props[key]:
            return str(props[key])
    # dernier recours : le premier champ texte non vide
    for v in props.values():
        if isinstance(v, str) and v.strip():
            return v
    return "Quartier inconnu"


# --- 2. Ventes DVF géolocalisées -----------------------------------------


def fetch_dvf_department_year(year: int) -> pd.DataFrame | None:
    url = f"https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/departements/{DEPARTEMENT}.csv.gz"
    try:
        log(f"Téléchargement DVF {year} pour le département {DEPARTEMENT} ...")
        r = requests.get(url, timeout=180)
        if r.status_code == 404:
            log(f"  pas de fichier pour {year} (404), on ignore.")
            return None
        r.raise_for_status()
        raw = gzip.decompress(r.content)
        df = pd.read_csv(io.BytesIO(raw), dtype={"code_commune": str}, low_memory=False)
        log(f"  -> {len(df)} lignes brutes pour le département.")
        return df
    except Exception as e:  # noqa: BLE001
        log(f"  échec pour {year} : {e}")
        return None


def fetch_ventes_orleans() -> pd.DataFrame:
    this_year = date.today().year
    frames = []
    for year in (this_year, this_year - 1, this_year - 2):
        df = fetch_dvf_department_year(year)
        if df is not None:
            frames.append(df)
    if not frames:
        raise RuntimeError("Aucune donnée DVF n'a pu être téléchargée.")

    all_df = pd.concat(frames, ignore_index=True)
    df = all_df[all_df["code_commune"] == INSEE_COMMUNE].copy()
    log(f"{len(df)} lignes DVF pour la commune d'Orléans ({INSEE_COMMUNE}).")

    df = df[df["nature_mutation"] == "Vente"]
    df = df[df["type_local"].isin(TYPES_LOCAUX_RETENUS)]
    df = df.dropna(subset=["valeur_fonciere", "latitude", "longitude", "date_mutation"])
    df = df[df["valeur_fonciere"] > 0]

    # Une même mutation (id_mutation) peut apparaitre sur plusieurs lignes
    # (plusieurs lots pour un seul bien) : on regroupe pour ne pas compter
    # le même prix plusieurs fois et additionner les surfaces.
    agg = (
        df.groupby("id_mutation")
        .agg(
            date_mutation=("date_mutation", "first"),
            valeur_fonciere=("valeur_fonciere", "first"),
            type_local=("type_local", "first"),
            surface_reelle_bati=("surface_reelle_bati", "sum"),
            nombre_pieces_principales=("nombre_pieces_principales", "sum"),
            adresse_numero=("adresse_numero", "first"),
            adresse_nom_voie=("adresse_nom_voie", "first"),
            code_postal=("code_postal", "first"),
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
        )
        .reset_index()
    )

    agg["date_mutation"] = pd.to_datetime(agg["date_mutation"])
    agg = agg[agg["surface_reelle_bati"] > 0]

    max_date = agg["date_mutation"].max()
    start_date = max_date - timedelta(days=365)
    agg = agg[agg["date_mutation"] >= start_date]

    agg["prix_m2"] = (agg["valeur_fonciere"] / agg["surface_reelle_bati"]).round(0)

    log(f"{len(agg)} ventes retenues entre {start_date.date()} et {max_date.date()}.")
    return agg


# --- 3. Association vente <-> quartier -----------------------------------


def assign_quartiers(ventes: pd.DataFrame, quartiers_geojson: dict) -> list[dict]:
    polygons = []
    for feature in quartiers_geojson["features"]:
        polygons.append((quartier_name(feature["properties"]), shape(feature["geometry"])))

    records = []
    non_assignees = 0
    for _, row in ventes.iterrows():
        point = Point(row["longitude"], row["latitude"])
        quartier = None
        for name, poly in polygons:
            if poly.contains(point):
                quartier = name
                break
        if quartier is None:
            non_assignees += 1
            continue

        adresse = " ".join(
            str(part) for part in (row["adresse_numero"], row["adresse_nom_voie"]) if pd.notna(part)
        ).strip()

        records.append(
            {
                "id": row["id_mutation"],
                "quartier": quartier,
                "date": row["date_mutation"].strftime("%Y-%m-%d"),
                "type_local": row["type_local"],
                "prix": int(row["valeur_fonciere"]),
                "surface_m2": int(row["surface_reelle_bati"]),
                "prix_m2": int(row["prix_m2"]),
                "pieces": int(row["nombre_pieces_principales"])
                if pd.notna(row["nombre_pieces_principales"])
                else None,
                "adresse": adresse or None,
                "code_postal": row["code_postal"],
                "lat": row["latitude"],
                "lon": row["longitude"],
            }
        )

    log(f"{non_assignees} ventes hors des contours de quartiers connus (ignorées).")
    return records


# --- Main -----------------------------------------------------------------


def main() -> None:
    quartiers_geojson = fetch_quartiers()
    ventes_df = fetch_ventes_orleans()
    ventes = assign_quartiers(ventes_df, quartiers_geojson)

    counts: dict[str, int] = {}
    for v in ventes:
        counts[v["quartier"]] = counts.get(v["quartier"], 0) + 1

    dates = [v["date"] for v in ventes]
    meta = {
        "generated_at": date.today().isoformat(),
        "commune": "Orléans",
        "code_insee": INSEE_COMMUNE,
        "nb_ventes": len(ventes),
        "periode_debut": min(dates) if dates else None,
        "periode_fin": max(dates) if dates else None,
        "ventes_par_quartier": counts,
        "source_ventes": "DVF géolocalisées - data.gouv.fr (files.data.gouv.fr/geo-dvf)",
        "source_quartiers": "Orléans Métropole - Open Data (data.orleans-metropole.fr)",
    }

    with open(f"{OUT_DIR}/quartiers.geojson", "w", encoding="utf-8") as f:
        json.dump(quartiers_geojson, f, ensure_ascii=False)
    with open(f"{OUT_DIR}/ventes.json", "w", encoding="utf-8") as f:
        json.dump(ventes, f, ensure_ascii=False)
    with open(f"{OUT_DIR}/meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    log("Terminé.")
    log(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
