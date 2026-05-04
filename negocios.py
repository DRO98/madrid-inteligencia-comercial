"""
Selección y ranking de locales por sector, público, renta, presupuesto y señales de mercado.

Motor principal del proyecto para filtrar y priorizar locales con señales de mercado y demografía.
"""

from __future__ import annotations

import hashlib
import html
import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

MIN_LOCALES_EPIGRAFE_MADRID = 100

# clave interna → (etiqueta UI, columna score demografía en el censo)
PUBLICO_LABEL_Y_SCORE: dict[str, tuple[str, str]] = {
    "joven": ("Gen Z / joven (15–24)", "score_joven_real"),
    "millennial": ("Profesionales jóvenes (25–39)", "score_millennial_real"),
    "familiar": ("Familias / adultos (40–64)", "score_familiar_real"),
    "senior": ("Senior (65+)", "score_senior_real"),
}

# Perfil renta por cuantiles sobre el subconjunto actual
PERFIL_RENTA_LABEL: dict[str, str] = {
    "cualquiera": "Cualquiera",
    "premium": "Mercado premium (alta renta)",
    "estandar": "Mercado estándar / volumen (renta media-baja)",
}

# Pesos score final (suman 1). Tránsito va aparte para maximizarlo explícitamente.
W_DEMografia = 0.25
W_COMP_HUECO = 0.20
W_TRANSITO_FIJO = 0.25
W_ATRACTIVO = 0.30

# Atractivo = combinación sin tránsito (el tránsito ya entra en W_TRANSITO_FIJO).
W_ATR_TURISMO = 0.30
W_ATR_VUT = 0.15
W_ATR_POBLACION = 0.30
W_ATR_PEATONES = 0.25

RADIO_VECINOS_COMP_M = 350.0

# Metros cuadrados de local no vienen en el censo: modelo sintético (hasta cruzar Idealista u otra fuente).
# Reglas por epígrafe (primera coincidencia gana) + ajuste por acceso, terraza y aforo exterior.
# Distribución: N(μ,σ) truncada a [lo,hi] con z ~ N(0,1) determinista por id_local.
METROS_LOCAL_SINTETICO_COL = "metros_local_sintetico"
ALQUILER_MES_SINTETICO_COL = "alquiler_mes_local_sintetico"

# (regex epígrafe, μ, σ, mín, máx) — μ/σ en m²; σ controla variabilidad entre locales del mismo epígrafe.
_METROS_REG_EPIGRAFE: list[tuple[str, float, float, float, float]] = [
    (r"TEATRO|CINE|AUDITORIO|ESPECTACULO|ESCENIC", 2200, 600, 400, 14_000),
    (r"EDUCACION UNIVERSITARIA|UNIVERSIDAD|COLEGIOS MAYORES|COLEGIO|INFANTIL Y PRIMARIA|EDUCACION", 1200, 400, 200, 8000),
    (r"GIMNASIO|CLUBES DEPORTIV", 850, 260, 200, 5000),
    (r"DEPOSITO|ALMACEN", 400, 120, 80, 4000),
    (r"HIPERMERCADO|SUPERMERCADO", 520, 150, 180, 6000),
    (r"MATERIALES DE CONSTRUCCION|BRICOLAJE", 360, 100, 100, 2500),
    (r"IMPRENTA", 300, 88, 90, 1800),
    (r"TALLER.*AUTOMOV|REPARACION.*AUTOMOV", 430, 130, 120, 3000),
    (r"SALONES DE BANQUETES", 450, 130, 130, 3500),
    (r"RESTAURANTE|BAR CON COCINA|TABERNA|CAFETER", 210, 78, 60, 1100),
    (r"OBRADOR|BARRA DEGUSTACION", 135, 48, 45, 650),
    (r"SIN OBRADOR", 60, 22, 22, 320),
    (r"CAFE, INFUSIONES|CAFÉ, INFUSIONES", 85, 30, 32, 400),
    (r"ESTOMATOLOGO|ODONTOLOGO|OPTICO|OPTOMETRISTA", 115, 40, 45, 550),
    (r"BELLEZA|PELUQUER", 85, 30, 32, 350),
    (r"ARREGLO DE ROPA", 40, 12, 18, 110),
    (r"PROMOCION INMOBILIARIA|INTERMEDIARIOS DEL COMERCIO", 110, 40, 40, 500),
    (r"INGENIERIA|INVESTIGACION Y DESARROLLO|DISENO ESPECIALIZADO|DISEÑO ESPECIALIZADO", 170, 55, 55, 800),
    (r"VIVIENDAS TUR", 75, 28, 30, 220),
    (r"COMERCIO AL POR MENOR", 88, 34, 28, 480),
    (r"COMERCIO AL POR MAYOR", 220, 70, 80, 1800),
    (r"ACTIVIDADES DE LOS SEGUROS|OFICINAS|DESPACHO", 130, 48, 45, 700),
    (r"HOSTAL|HOSPEDAJE|MOTEL", 380, 110, 120, 2500),
    (r"FARMACIA", 190, 55, 80, 600),
    (r"LIBRERIA|PAPEL|PAPELER", 95, 32, 35, 400),
    (r"FLORISTERIA|PLANTAS", 72, 26, 28, 320),
]

_METROS_DEFAULT = (92.0, 38.0, 24.0, 520.0)

def _z_normal_por_id(id_local: np.ndarray) -> np.ndarray:
    """N(0,1) determinista por fila (Box–Muller a partir de MD5 del id)."""
    out = np.empty(len(id_local), dtype=np.float64)
    for i, lid in enumerate(id_local):
        d = hashlib.md5(str(lid).encode("utf-8")).digest()
        u1 = int.from_bytes(d[:8], "big") / 2**64
        u2 = int.from_bytes(d[8:16], "big") / 2**64
        u1 = max(float(u1), 1e-12)
        out[i] = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * float(u2))
    return out


def _factor_acceso_local(series_acceso: pd.Series) -> np.ndarray:
    """Factores discretos según valores típicos del censo (Puerta Calle, Interior, Agrupado, PC Asociado)."""
    v = series_acceso.fillna("Puerta Calle").astype(str).str.strip().str.lower()
    fac = np.ones(len(v), dtype=np.float64)
    fac = np.where(v == "interior", 0.90, fac)
    fac = np.where(v == "agrupado", 1.06, fac)
    fac = np.where(v == "pc asociado", 1.03, fac)
    return fac


def asignar_metros_cuadrados_sinteticos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Añade `metros_local_sintetico`: m² plausibles por local (modelo; reemplazar con datos reales si existen).
    """
    if METROS_LOCAL_SINTETICO_COL in df.columns and df[METROS_LOCAL_SINTETICO_COL].notna().all():
        return df

    out = df.copy()
    n = len(out)
    d_mu, d_sig, d_lo, d_hi = _METROS_DEFAULT
    mu = np.full(n, d_mu, dtype=np.float64)
    sig = np.full(n, d_sig, dtype=np.float64)
    lo = np.full(n, d_lo, dtype=np.float64)
    hi = np.full(n, d_hi, dtype=np.float64)
    assigned = np.zeros(n, dtype=bool)
    ep = out["desc_epigrafe"].fillna("").astype(str)

    for pat, m, s, l, h in _METROS_REG_EPIGRAFE:
        msk = (~assigned) & ep.str.contains(pat, case=False, na=False, regex=True)
        msk_a = msk.to_numpy()
        mu[msk_a] = m
        sig[msk_a] = s
        lo[msk_a] = l
        hi[msk_a] = h
        assigned |= msk_a

    cap = out.get("capacidad_exterior_total")
    if cap is not None:
        capv = cap.fillna(0).astype(float).to_numpy()
        capv = np.clip(capv, 0, 5000)
    else:
        capv = np.zeros(n, dtype=np.float64)
    bonus_m = np.minimum(90.0, 5.5 * np.sqrt(capv + 1.0))

    terr = out.get("terraza_acondicionada")
    if terr is not None:
        f_terr = np.where(terr.fillna(0).astype(float).to_numpy() >= 0.5, 1.08, 1.0)
    else:
        f_terr = np.ones(n, dtype=np.float64)

    acc = out["desc_tipo_acceso_local"] if "desc_tipo_acceso_local" in out.columns else pd.Series("Puerta Calle", index=out.index)
    f_acc = _factor_acceso_local(acc)

    mu_adj = (mu + bonus_m) * f_acc * f_terr
    sig_adj = sig * (0.88 + 0.06 * f_acc)

    z = _z_normal_por_id(out["id_local"].to_numpy())
    m2 = np.clip(mu_adj + sig_adj * z, lo, hi)
    out[METROS_LOCAL_SINTETICO_COL] = np.round(m2, 1)
    return out


def preparar_tabla_negocios(df: pd.DataFrame) -> pd.DataFrame:
    """Proyección WGS84 si falta + metros sintéticos para todo el dataset."""
    out = ensure_lat_lon(df)
    return asignar_metros_cuadrados_sinteticos(out)


def conteos_locales_por_epigrafe_madrid(df: pd.DataFrame) -> pd.Series:
    base = df.dropna(subset=["desc_epigrafe", "id_local"])
    return base.groupby("desc_epigrafe")["id_local"].nunique()


def lista_epigrafes_con_soporte(
    df: pd.DataFrame,
    min_locales: int | None = None,
) -> list[str]:
    umbral = min_locales if min_locales is not None else MIN_LOCALES_EPIGRAFE_MADRID
    cnt = conteos_locales_por_epigrafe_madrid(df)
    return sorted(cnt[cnt >= umbral].index.astype(str).tolist())


def ensure_lat_lon(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if (
        "lat" in out.columns
        and "lon" in out.columns
        and out["lat"].notna().any()
        and out["lon"].notna().any()
    ):
        return out
    if "coordenada_x_local" not in out.columns or "coordenada_y_local" not in out.columns:
        return out
    try:
        from pyproj import Transformer
    except ImportError:
        return out

    t = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)
    mask = out["coordenada_x_local"].notna() & out["coordenada_y_local"].notna()
    lon = np.full(len(out), np.nan, dtype=float)
    lat = np.full(len(out), np.nan, dtype=float)
    if mask.any():
        xs = out.loc[mask, "coordenada_x_local"].astype(float).to_numpy()
        ys = out.loc[mask, "coordenada_y_local"].astype(float).to_numpy()
        lon_m, lat_m = t.transform(xs, ys)
        lon[mask.to_numpy()] = lon_m
        lat[mask.to_numpy()] = lat_m
    out["lon"] = lon
    out["lat"] = lat
    return out


def margen_presupuesto_dinamico(presupuesto: float) -> float:
    """
    Semiancho de la banda aceptable alrededor del presupuesto objetivo.
    Interpolación lineal: 500 € → ±200 €, 10 000 € → ±2500 €;
    por debajo de 500 se mantiene 200 €; por encima de 10 000 se extrapola con suavizado.
    """
    p = float(np.clip(presupuesto, 400.0, 200_000.0))
    if p <= 500.0:
        return 200.0
    if p >= 10_000.0:
        extra = min((p - 10_000.0) * 0.0125, 1_500.0)
        return float(min(2500.0 + extra, 5_000.0))
    t = (p - 500.0) / (10_000.0 - 500.0)
    return 200.0 + t * (2500.0 - 200.0)


def _safe_norm(series: pd.Series) -> pd.Series:
    s = series.fillna(0.0).astype(float)
    mx = float(s.max())
    mn = float(s.min())
    if mx <= mn or np.isnan(mx) or np.isnan(mn):
        return pd.Series(np.ones(len(s)), index=s.index)
    return (s - mn) / (mx - mn)


def score_atractivo_sin_transito(df: pd.DataFrame) -> pd.Series:
    """Turismo, VUT, población y peatones (log), sin tránsito — versión normalizada (solo uso interno)."""
    n_tur = _safe_norm(df["score_turismo"])
    n_vut = _safe_norm(df["UNIDADES_VUT"])
    n_pob = _safe_norm(np.log1p(df["poblacion_total"].fillna(0).astype(float)))
    n_pe = _safe_norm(np.log1p(df["peatones"].fillna(0).astype(float)))
    return (
        W_ATR_TURISMO * n_tur
        + W_ATR_VUT * n_vut
        + W_ATR_POBLACION * n_pob
        + W_ATR_PEATONES * n_pe
    )


def atractivo_bruto(df: pd.DataFrame) -> pd.Series:
    """Combinación lineal en escala real (sin min-max); sirve para percentiles interpretables."""
    return (
        W_ATR_TURISMO * df["score_turismo"].fillna(0).astype(float)
        + W_ATR_VUT * df["UNIDADES_VUT"].fillna(0).astype(float)
        + W_ATR_POBLACION * np.log1p(df["poblacion_total"].fillna(0).astype(float))
        + W_ATR_PEATONES * np.log1p(df["peatones"].fillna(0).astype(float))
    )


def normaliza_publico_keys(publico: str | Sequence[str] | None) -> tuple[list[str], str | None]:
    """Varias edades/públicos: deduplica y valida. Devuelve ([], error) si no hay ninguno válido."""
    if publico is None:
        return [], "No se indicó público objetivo."
    if isinstance(publico, str):
        raw = [publico]
    else:
        raw = list(publico)
    keys = [k for k in dict.fromkeys(raw) if k in PUBLICO_LABEL_Y_SCORE]
    if not keys:
        return [], "Ninguna clave de público válida (elige al menos un segmento)."
    return keys, None


def indice_percentil_muestra(s: pd.Series) -> pd.Series:
    """
    Posición relativa 0–100 dentro del conjunto filtrado (percentil).
    No son componentes que deban sumar 100 entre sí: cada uno mide «qué tan arriba va este local
    en esta dimensión respecto al resto de candidatos».
    """
    s = s.astype(float)
    if len(s) <= 1 or s.nunique(dropna=False) <= 1:
        return pd.Series(50.0, index=s.index)
    r = s.rank(pct=True, method="average")
    return (100.0 * r).round(1).clip(0.0, 100.0)


def competencia_vecinos_mismo_epigrafe(
    df_sector_coords: pd.DataFrame,
    df_candidatos: pd.DataFrame,
    radius_m: float = RADIO_VECINOS_COMP_M,
) -> np.ndarray:
    """
    Competidores mismo epígrafe en `radius_m` (sklearn BallTree + haversine).
    Si no hay sklearn o falla el árbol, proxy: locales del sector en el mismo barrio.
    """
    if df_candidatos.empty:
        return np.zeros(0, dtype=int)

    df_ref = df_sector_coords.dropna(subset=["lat", "lon", "id_local"]).copy()
    try:
        from sklearn.neighbors import BallTree
    except ImportError:
        return _competencia_fallback_barrio(df_sector_coords, df_candidatos)

    if df_ref.empty:
        return _competencia_fallback_barrio(df_sector_coords, df_candidatos)

    try:
        coords_ref = np.radians(df_ref[["lat", "lon"]].astype(float).values)
        tree = BallTree(coords_ref, metric="haversine")
        r_rad = radius_m / 6_371_000.0
        coords_q = np.radians(df_candidatos[["lat", "lon"]].astype(float).values)
        ids_ref = df_ref["id_local"].values
        qids = df_candidatos["id_local"].values
        lists = tree.query_radius(coords_q, r=r_rad)
        out = np.zeros(len(df_candidatos), dtype=int)
        for i, neigh in enumerate(lists):
            qid = qids[i]
            out[i] = sum(1 for j in neigh if ids_ref[j] != qid)
        return out
    except Exception:
        return _competencia_fallback_barrio(df_sector_coords, df_candidatos)


def _competencia_fallback_barrio(
    df_sector: pd.DataFrame,
    df_candidatos: pd.DataFrame,
) -> np.ndarray:
    if df_sector.empty or "desc_barrio_local" not in df_sector.columns:
        return np.zeros(len(df_candidatos), dtype=int)
    nu = df_sector.groupby("desc_barrio_local", observed=False)["id_local"].nunique()
    mapped = df_candidatos["desc_barrio_local"].map(nu).fillna(0).astype(int).to_numpy()
    return np.maximum(mapped - 1, 0)


def _filtro_perfil_renta(df: pd.DataFrame, perfil_renta: str) -> pd.DataFrame:
    if perfil_renta == "premium":
        q = df["renta_neta_hogares"].astype(float).quantile(0.60)
        return df.loc[df["renta_neta_hogares"].astype(float) >= q]
    if perfil_renta == "estandar":
        q = df["renta_neta_hogares"].astype(float).quantile(0.55)
        return df.loc[df["renta_neta_hogares"].astype(float) <= q]
    return df


def negocios_scored(
    df: pd.DataFrame,
    tipo_negocio: str,
    publico_objetivo: str | Sequence[str],
    presupuesto: float,
    metros_requeridos: float,
    perfil_renta: str = "cualquiera",
) -> dict[str, Any]:
    keys_pub, err_pub = normaliza_publico_keys(publico_objetivo)
    meta: dict[str, Any] = {
        "publico_keys": keys_pub,
        "publico_labels": [PUBLICO_LABEL_Y_SCORE[k][0] for k in keys_pub],
        "perfil_renta": perfil_renta,
    }

    if err_pub:
        meta["error"] = err_pub
        return {"locales": pd.DataFrame(), "barrios": [], "meta": meta}

    if perfil_renta not in PERFIL_RENTA_LABEL:
        meta["error"] = "perfil_renta inválido"
        return {"locales": pd.DataFrame(), "barrios": [], "meta": meta}

    if METROS_LOCAL_SINTETICO_COL not in df.columns or df[METROS_LOCAL_SINTETICO_COL].isna().any():
        df = asignar_metros_cuadrados_sinteticos(df)

    cols_demo = [PUBLICO_LABEL_Y_SCORE[k][1] for k in keys_pub]
    meta["cols_demo_combinadas"] = cols_demo

    m_pres = margen_presupuesto_dinamico(presupuesto)
    meta["margen_presupuesto"] = int(round(float(m_pres)))

    df_filtrado = df.loc[df["desc_epigrafe"] == tipo_negocio].copy()
    if df_filtrado.empty:
        return {"locales": pd.DataFrame(), "barrios": [], "meta": meta}

    combo_demo = df_filtrado[cols_demo].astype(float).mean(axis=1)
    media = float(combo_demo.mean())
    std = float(combo_demo.std())
    if np.isnan(std):
        std = 0.0
    umbral_demo = media - std
    df_filtrado = df_filtrado.loc[combo_demo >= umbral_demo]

    df_filtrado = df_filtrado.assign(
        coste_estimado=metros_requeridos * df_filtrado["precio_m2_real"].astype(float)
    )
    df_filtrado = df_filtrado.loc[
        (df_filtrado["coste_estimado"] >= presupuesto - m_pres)
        & (df_filtrado["coste_estimado"] <= presupuesto + m_pres)
    ]

    if "renta_neta_hogares" in df_filtrado.columns:
        df_filtrado = _filtro_perfil_renta(df_filtrado, perfil_renta)

    if df_filtrado.empty:
        return {"locales": pd.DataFrame(), "barrios": [], "meta": meta}

    combo_f = df_filtrado[cols_demo].astype(float).mean(axis=1)

    df_sector = df.loc[df["desc_epigrafe"] == tipo_negocio].dropna(subset=["lat", "lon"])
    df_sector = df_sector[
        df_sector["lat"].between(40.28, 40.58) & df_sector["lon"].between(-3.95, -3.52)
    ]

    counts = competencia_vecinos_mismo_epigrafe(df_sector, df_filtrado, RADIO_VECINOS_COMP_M)
    serie_vecinos = pd.Series(counts, index=df_filtrado.index, dtype=int)

    n_demo = _safe_norm(combo_f)
    n_hueco = 1.0 - _safe_norm(serie_vecinos.astype(float))
    n_trans = _safe_norm(df_filtrado["score_transito"])
    n_atr = score_atractivo_sin_transito(df_filtrado)

    score_final = (
        W_DEMografia * n_demo
        + W_COMP_HUECO * n_hueco
        + W_TRANSITO_FIJO * n_trans
        + W_ATRACTIVO * n_atr
    )

    hueco_bruto = 1.0 / (1.0 + serie_vecinos.astype(float))
    atr_br = atractivo_bruto(df_filtrado)

    pm2 = df_filtrado["precio_m2_real"].astype(float)
    mloc = df_filtrado[METROS_LOCAL_SINTETICO_COL].astype(float)
    alq_local = (pm2 * mloc).round(0)

    df_filtrado = df_filtrado.assign(
        n_vecinos_epigrafe_m=serie_vecinos,
        combo_demo_censo=combo_f.round(2),
        score_final=score_final,
        indice_demografia=indice_percentil_muestra(combo_f),
        indice_competencia=indice_percentil_muestra(hueco_bruto),
        indice_transito=indice_percentil_muestra(df_filtrado["score_transito"].astype(float)),
        indice_atractivo=indice_percentil_muestra(atr_br),
        indice_global=indice_percentil_muestra(score_final),
        **{ALQUILER_MES_SINTETICO_COL: alq_local},
    )

    df_ranked = df_filtrado.sort_values("score_final", ascending=False)
    top_locales = df_ranked.head(20).copy()
    top_locales.drop(columns=["score_final"], inplace=True, errors="ignore")

    top_barrios = (
        top_locales["desc_barrio_local"]
        .value_counts()
        .head(5)
        .index.astype(str)
        .tolist()
    )

    meta["n_candidatos_tras_filtros"] = int(len(df_filtrado))
    return {"locales": top_locales, "barrios": top_barrios, "meta": meta}


def popup_mapa_breve_html(row: pd.Series) -> str:
    """Texto corto dentro del mapa; la ficha larga va en el panel lateral."""
    bar = html.escape(str(row.get("desc_barrio_local", "—"))[:40])
    ep_raw = str(row.get("desc_epigrafe", ""))
    suf = "…" if len(ep_raw) > 50 else ""
    ep_short = html.escape(ep_raw[:50] + suf)
    return (
        '<div class="popup-map-mini">'
        f"<strong>{bar}</strong>"
        f'<div class="popup-map-mini-epi">{ep_short}</div>'
        '<div class="popup-map-mini-hint">Ver ficha completa al lado →</div>'
        "</div>"
    )


def popup_marcador_streamlit_html(row: pd.Series, ix: int) -> str:
    """Popup compacto + índice oculto para que Streamlit sepa qué fila mostrar en el panel."""
    return popup_mapa_breve_html(row) + f'<span style="display:none" data-midx="{int(ix)}"></span>'


def ficha_local_html(row: pd.Series) -> str:
    """Ficha completa (panel lateral / web); HTML seguro."""
    bar = html.escape(str(row.get("desc_barrio_local", "—")))
    acceso = html.escape(str(row.get("desc_tipo_acceso_local", "—")))
    try:
        cm = float(row.get("coste_estimado", float("nan")))
        cm_s = f"{cm:,.0f} €/mes" if np.isfinite(cm) else "—"
    except (TypeError, ValueError):
        cm_s = "—"
    try:
        alq_loc = float(row.get(ALQUILER_MES_SINTETICO_COL, float("nan")))
        alq_loc_s = f"{alq_loc:,.0f} €/mes" if np.isfinite(alq_loc) else "—"
    except (TypeError, ValueError):
        alq_loc_s = "—"
    try:
        m2_loc = float(row.get(METROS_LOCAL_SINTETICO_COL, float("nan")))
        m2_loc_s = f"{m2_loc:.1f} m²" if np.isfinite(m2_loc) else "—"
    except (TypeError, ValueError):
        m2_loc_s = "—"
    try:
        pm = float(row.get("precio_m2_real", float("nan")))
        pm_s = f"{pm:.2f} €/m²" if np.isfinite(pm) else "—"
    except (TypeError, ValueError):
        pm_s = "—"

    def _f(x: Any, nd: int = 3) -> str:
        try:
            v = float(x)
            if np.isfinite(v):
                return f"{v:.{nd}f}"
        except (TypeError, ValueError):
            pass
        return "—"

    ig = _f(row.get("indice_global"), 1)
    nv = row.get("n_vecinos_epigrafe_m", "—")
    try:
        nv_s = str(int(nv)) if pd.notna(nv) else "—"
    except (TypeError, ValueError):
        nv_s = "—"

    return (
        '<div class="local-ficha-inner">'
        f'<p class="ficha-line"><span class="ficha-etiq">Barrio</span><br/>{bar}</p>'
        f'<p class="ficha-line"><span class="ficha-etiq">Acceso</span><br/>{acceso}</p>'
        f'<p class="ficha-line"><span class="ficha-etiq">Superficie local</span><br/>{html.escape(m2_loc_s)}</p>'
        "<p class=\"ficha-line\"><span class=\"ficha-etiq\">Alquiler mensual aproximado</span><br/>"
        f"{html.escape(alq_loc_s)} <span class=\"ficha-sub\">({html.escape(pm_s)})</span></p>"
        f'<p class="ficha-line"><span class="ficha-etiq">Tu presupuesto en la búsqueda</span><br/>{html.escape(cm_s)}</p>'
        "<p class=\"ficha-line\"><span class=\"ficha-etiq\">Frente al resto de opciones</span><br/>"
        f"<span class=\"ficha-sub\">0–100 (más alto mejor):</span> {html.escape(ig)}</p>"
        "<p class=\"ficha-line\"><span class=\"ficha-etiq\">Locales del mismo sector muy cerca</span><br/>"
        f"<span class=\"ficha-sub\">({RADIO_VECINOS_COMP_M:.0f} m):</span> {html.escape(nv_s)}</p>"
        "</div>"
    )


def popup_html_local(row: pd.Series) -> str:
    """Compatibilidad: misma ficha completa que `ficha_local_html`."""
    return ficha_local_html(row)

