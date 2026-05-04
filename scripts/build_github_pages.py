"""
Genera sitio estático en `docs/` para GitHub Pages:
  - Dataset ligero gzip + lat/lon
  - `main.py` unificado para PyScript (misma lógica que Streamlit)

Requiere: pandas, pyproj

  pip install pandas pyproj
  python scripts/build_github_pages.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
_DOCS = _REPO / "docs"
_SCRIPTS = Path(__file__).resolve().parent
_SRC_CSV = _REPO / "data" / "processed" / "negocios_scored.csv"
_OUT_GZ = _DOCS / "data" / "negocios_web.csv.gz"


WEB_COLUMNS = [
    "id_local",
    "desc_barrio_local",
    "desc_epigrafe",
    "desc_tipo_acceso_local",
    "es_nocturno",
    "capacidad_exterior_total",
    "terraza_acondicionada",
    "score_joven_real",
    "score_millennial_real",
    "score_familiar_real",
    "score_senior_real",
    "renta_neta_hogares",
    "score_turismo",
    "peatones",
    "score_transito",
    "UNIDADES_VUT",
    "poblacion_total",
    "precio_m2_real",
    "porcentaje_mujeres_real",
    "pension_media_real",
    "tasa_supervivencia_real",
    "coordenada_x_local",
    "coordenada_y_local",
]


def _utm_to_wgs84(df: pd.DataFrame) -> pd.DataFrame:
    try:
        from pyproj import Transformer
    except ImportError as exc:
        raise RuntimeError(
            "Instala pyproj para proyectar coordenadas: pip install pyproj"
        ) from exc

    t = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)
    x = df["coordenada_x_local"].astype(float)
    y = df["coordenada_y_local"].astype(float)
    lon, lat = t.transform(x.to_numpy(), y.to_numpy())
    out = df.copy()
    out["lon"] = lon
    out["lat"] = lat
    out.drop(columns=["coordenada_x_local", "coordenada_y_local"], inplace=True)
    return out


def _read_py_source(path: Path) -> str:
    """Lee fuente UTF-8 y quita BOM (Pyodide no tolera U+FEFF en medio del código)."""
    text = path.read_text(encoding="utf-8-sig")
    # utf-8-sig ya quita BOM inicial; por si viera \ufeff residual:
    while text.startswith("\ufeff"):
        text = text[1:]
    return text


def _build_bundle() -> str:
    neg = _read_py_source(_REPO / "negocios.py")
    frag = _read_py_source(_SCRIPTS / "web_pyscript_app.py")
    return (
        "# -*- coding: utf-8 -*-\n# Generado por scripts/build_github_pages.py — no editar.\n\n"
        + neg.strip()
        + "\n\n"
        + frag.strip()
        + "\n"
    )


def main() -> int:
    if not _SRC_CSV.is_file():
        print("No encuentro:", _SRC_CSV, file=sys.stderr)
        return 1

    (_DOCS / "data").mkdir(parents=True, exist_ok=True)

    print("Leyendo CSV y exportando subset + lat/lon...")
    df = pd.read_csv(_SRC_CSV, usecols=lambda c: c in WEB_COLUMNS)
    df = _utm_to_wgs84(df)

    df.to_csv(
        _OUT_GZ,
        index=False,
        compression={
            "method": "gzip",
            "compresslevel": 9,
            "mtime": 0,
        },
    )
    gz_mb = _OUT_GZ.stat().st_size / (1024 * 1024)
    print(f"  Escrito {_OUT_GZ.name} (~{gz_mb:.2f} MB)")

    bundle_path = _DOCS / "main.py"
    bundle_path.write_text(_build_bundle(), encoding="utf-8", newline="\n")
    print("  Escrito", bundle_path.relative_to(_REPO))

    print("Listo. Activa GitHub Pages con carpeta /docs en Settings.")
    print("Local test: cd docs  then  python -m http.server 8000  then open http://localhost:8000/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
