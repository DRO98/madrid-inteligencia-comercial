from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from src.features.nocturnidad import serie_nocturno_por_epigrafe

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ML_PRED_CSV = _REPO_ROOT / "data" / "processed" / "market_density_lgbm.csv"

# Mínimo de locales distintos en Madrid (censo) por epígrafe para considerar el sector usable en la UI y el ranking.
MIN_LOCALES_EPIGRAFE_MADRID = 100

# Si el epígrafe tiene menos locales que este umbral en todo Madrid, exige ≥1 local de ese epígrafe por barrio
# para entrar al ranking (evita competencia_directa=0 que hincha la rama multiplicativa sin oferta censada).
MAX_LOCALES_EPIGRAFE_PARA_FILTRO_COMPETENCIA_BARRIO = 500


def _aliases_columnas_censo(df: pd.DataFrame) -> pd.DataFrame:
    """Alinea nombres del CSV regenerado desde notebooks con lo que espera el ranking."""
    out = df
    if "capacidad_exterior" not in out.columns and "capacidad_exterior_total" in out.columns:
        out = out.rename(columns={"capacidad_exterior_total": "capacidad_exterior"})
    return out


def conteos_locales_por_epigrafe_madrid(df: pd.DataFrame) -> pd.Series:
    """Serie epígrafe → número de id_local distintos en todo el municipio (dataset Madrid)."""
    base = df.dropna(subset=["desc_epigrafe", "id_local"])
    return base.groupby("desc_epigrafe")["id_local"].nunique()


def lista_epigrafes_con_soporte(
    df: pd.DataFrame,
    min_locales: int | None = None,
) -> list[str]:
    """
    Epígrafes con al menos `min_locales` id_local distintos en todo el dataset (Madrid).
    Si min_locales es None, se usa MIN_LOCALES_EPIGRAFE_MADRID.
    """
    umbral = min_locales if min_locales is not None else MIN_LOCALES_EPIGRAFE_MADRID
    counts = conteos_locales_por_epigrafe_madrid(df)
    elegibles = counts[counts >= umbral].index.astype(str).tolist()
    return sorted(elegibles)


@lru_cache(maxsize=1)
def _load_market_density_preds() -> pd.DataFrame | None:
    if not _ML_PRED_CSV.is_file():
        return None
    return pd.read_csv(_ML_PRED_CSV)


def generar_ranking_barrios(
    df: pd.DataFrame,
    epigrafe_objetivo: str,
    peso_eco: float = 5.0,
    peso_terraza: float = 5.0,
    perfil_renta: str = "Cualquiera",
    target_edad: str = "Todos",
    genero_objetivo: str = "Ambos",
    horario_objetivo: str = "Indiferente",
    metros_cuadrados: int = 100,
    presupuesto_max: float = 3000.0,
    importancia_turismo: float = 50.0,
    importancia_transito: float = 50.0,
    tolerancia_supervivencia: float = 50.0,
) -> pd.DataFrame:
    min_epi = MIN_LOCALES_EPIGRAFE_MADRID
    cnt_epi = int(conteos_locales_por_epigrafe_madrid(df).get(epigrafe_objetivo, 0))
    if cnt_epi < min_epi:
        return pd.DataFrame()

    def _safe_norm(series: pd.Series) -> pd.Series:
        s = series.fillna(0.0).astype(float)
        max_v = s.max()
        min_v = s.min()
        if max_v <= min_v:
            return pd.Series(np.ones(len(s)), index=s.index)
        return (s - min_v) / (max_v - min_v)

    # Nocturnidad por barrio: imputar es_nocturno por barrio×epígrafe, refuerzo por epígrafe nocturno típico (actividades.tsv cubre pocos locales).
    # Recalculamos siempre desde filas para no depender de una columna CSV desfasada ni del antiguo fillna(0) global.
    df_rank = _aliases_columnas_censo(df.drop(columns=["nocturnidad_barrio"], errors="ignore")).copy()
    # Vectorizado: evitar transform(lambda...) por grupo — con ~150k filas bloqueaba la UI minutos.
    _g = df_rank.groupby(["desc_barrio_local", "desc_epigrafe"], observed=False)["es_nocturno"]
    _means_epi = _g.transform("mean")
    _es_imp = df_rank["es_nocturno"].fillna(_means_epi).fillna(0.0)
    _es_imp = np.maximum(_es_imp.astype(float), serie_nocturno_por_epigrafe(df_rank["desc_epigrafe"]).astype(float))
    _nb = (
        df_rank.assign(_es_imp=_es_imp)
        .groupby("desc_barrio_local", observed=False)["_es_imp"]
        .mean()
        .reset_index()
        .rename(columns={"_es_imp": "nocturnidad_barrio"})
    )
    df_rank = df_rank.merge(_nb, on="desc_barrio_local", how="left")
    df_rank["nocturnidad_barrio"] = df_rank["nocturnidad_barrio"].fillna(0.0)

    # Mediana de nocturnidad municipal (un valor por barrio sobre todo el censo): bonus horario y filtro duro nocturno.
    med_nocturnidad_ciudad = float(
        df_rank.drop_duplicates(subset=["desc_barrio_local"])["nocturnidad_barrio"].median()
    )

    aggs = {
        "id_local": "count",
        "capacidad_exterior": "mean",
        "terraza_acondicionada": "mean",
        "nocturnidad_barrio": "first",
        "score_joven_real": "first",
        "score_millennial_real": "first",
        "score_familiar_real": "first",
        "score_senior_real": "first",
        "renta_neta_hogares": "first",
        "score_turismo": "first",
        "score_transito": "first",
        "peatones": "mean",
        "UNIDADES_VUT": "mean",
        "poblacion_total": "first",
        "precio_m2_real": "first",
        "porcentaje_mujeres_real": "first",
        "pension_media_real": "first",
        "tasa_supervivencia_real": "first",
    }

    barrios = df_rank.groupby("desc_barrio_local").agg(aggs).reset_index()
    barrios.rename(columns={"id_local": "locales_totales"}, inplace=True)

    # FILTRO: evitar barrios con poca representación
    barrios = barrios[barrios["locales_totales"] >= 15]

    comp = (
        df[df["desc_epigrafe"] == epigrafe_objetivo]
        .groupby("desc_barrio_local")
        .size()
        .reset_index(name="competencia_directa")
    )
    ranking = pd.merge(barrios, comp, on="desc_barrio_local", how="left").fillna(
        {"competencia_directa": 0}
    )

    if cnt_epi < MAX_LOCALES_EPIGRAFE_PARA_FILTRO_COMPETENCIA_BARRIO:
        ranking = ranking[ranking["competencia_directa"] >= 1]
        if ranking.empty:
            return pd.DataFrame()

    # --- DATOS REALES ---
    ranking["precio_m2_alquiler"] = ranking["precio_m2_real"]
    ranking["coste_alquiler_estimado"] = ranking["precio_m2_real"] * metros_cuadrados
    # CSV histórico: proporción 0–1. Si algún export viene ya en % (>1), no duplicar escala.
    _ts = ranking["tasa_supervivencia_real"].astype(float)
    ranking["tasa_supervivencia"] = np.where(_ts <= 1.0, _ts * 100.0, _ts)
    ranking["porcentaje_mujeres"] = ranking["porcentaje_mujeres_real"]
    ranking["pension_media"] = ranking["pension_media_real"]
    ranking["score_competencia"] = np.log1p(ranking["competencia_directa"])

    # --- FILTRO EXCLUYENTE PRECIO ---
    ranking = ranking[ranking["coste_alquiler_estimado"] <= presupuesto_max]
    if ranking.empty:
        return pd.DataFrame()
    
    # Eliminar barrios con población muy baja (evita outliers tipo El Pardo)
    ranking = ranking[ranking['poblacion_total'] >= 5000]

    # Filtro duro de supervivencia según slider del usuario
    # Con tolerancia 70 → umbral 59.5%, elimina barrios con supervivencia baja
    umbral_supervivencia = 85.0 * (tolerancia_supervivencia / 100.0)
    ranking = ranking[ranking['tasa_supervivencia'] >= umbral_supervivencia]
    if ranking.empty:
        return pd.DataFrame()

    # Ocio nocturno: filtro duro — umbral = mediana municipal fija (un valor por barrio en todo el censo), no la mediana del ranking ya filtrado.
    if horario_objetivo == "Ocio Nocturno / Tarde":
        ranking = ranking[ranking["nocturnidad_barrio"] >= med_nocturnidad_ciudad]
        if ranking.empty:
            return pd.DataFrame()

    # Filtro por clase social ANTES de construir score_* (si no, al recortar filas los Series quedan desalineados y revienta score_multiplicativo)
    if perfil_renta == "Barrios de Alta Renta (Premium)":
        umbral_renta_min = ranking["renta_neta_hogares"].quantile(0.60)
        ranking = ranking[ranking["renta_neta_hogares"] >= umbral_renta_min]
    elif perfil_renta == "Barrios de Renta Media/Baja (Volumen)":
        umbral_renta_max = ranking["renta_neta_hogares"].quantile(0.55)
        ranking = ranking[ranking["renta_neta_hogares"] <= umbral_renta_max]
    if ranking.empty:
        return pd.DataFrame()

    # -----------------------------------------------------------------------
    # SCORE BASE (corregido)
    # Antes: locales_totales/max * 50  → premiaba barrios grandes en general
    # Ahora: competencia_directa normalizada * 20 → premia mercado activo del epígrafe
    # -----------------------------------------------------------------------
    n_comp_base = _safe_norm(ranking["competencia_directa"])
    score_base = n_comp_base * 20  # máximo 20 pts (antes 50 pts con locales_totales)

    comp_ajustada = np.log1p(ranking["competencia_directa"]) + 1

    bonus_terr = (
        ranking["capacidad_exterior"]
        / (ranking["capacidad_exterior"].max() + 0.1)
        * peso_terraza
        * 5
    )
    bonus_eco = (
        ranking["terraza_acondicionada"]
        / (ranking["terraza_acondicionada"].max() + 0.1)
        * peso_eco
        * 5
    )

    # --- BONUS EDAD ---
    bonus_edad = 1.0
    if target_edad == "Estudiantes y Gen Z (15-24 años)":
        bonus_edad = ranking["score_joven_real"] / 20.0
    elif target_edad == "Profesionales Jóvenes (25-39 años)":
        bonus_edad = ranking["score_millennial_real"] / 20.0
    elif target_edad == "Familias / Edad Madura (40-64 años)":
        bonus_edad = ranking["score_familiar_real"] / 20.0
    elif target_edad == "Seniors y Jubilados (65+ años)":
        bonus_edad = (ranking["score_senior_real"] / 20.0) * (
            ranking["pension_media"] / 1200.0
        )

    # --- BONUS GÉNERO ---
    bonus_genero = 1.0
    if genero_objetivo == "Mujeres (Público Femenino)":
        bonus_genero = ranking["porcentaje_mujeres"] / 50.0
    elif genero_objetivo == "Hombres (Público Masculino)":
        bonus_genero = (100 - ranking["porcentaje_mujeres"]) / 50.0

    # --- BONUS RENTA (el filtro por perfil ya se aplicó arriba) ---
    bonus_renta = 1.0

    # --- BONUS HORARIO: referencia = mediana ciudad (no la de los barrios ya filtrados; si no, todos parecen "nocturnos") ---
    ref_noc = med_nocturnidad_ciudad
    if horario_objetivo == "Ocio Nocturno / Tarde":
        bonus_horario = np.where(
            ranking["nocturnidad_barrio"] >= ref_noc, 1.65, 0.55
        )
    elif horario_objetivo == "Diurno / Estándar":
        bonus_horario = np.where(
            ranking["nocturnidad_barrio"] <= ref_noc, 1.65, 0.55
        )
    else:
        bonus_horario = 1.0

    # -----------------------------------------------------------------------
    # NORMALIZACIÓN DE SEÑALES (cada variable aparece UNA sola vez)
    # -----------------------------------------------------------------------
    n_nocturnidad_barrio = _safe_norm(ranking["nocturnidad_barrio"])
    n_transito     = _safe_norm(ranking["score_transito"])
    n_peatones     = _safe_norm(ranking["peatones"])
    n_poblacion    = _safe_norm(ranking["poblacion_total"])
    n_turismo      = _safe_norm(ranking["score_turismo"])
    n_vut          = _safe_norm(ranking["UNIDADES_VUT"])
    n_supervivencia = _safe_norm(ranking["tasa_supervivencia"])
    n_competencia  = _safe_norm(ranking["score_competencia"])

    # -----------------------------------------------------------------------
    # SCORE DEMANDA: tránsito aparece UNA sola vez aquí (corregido)
    # Antes: tránsito aparecía en score_demanda + score_atractor + término propio
    # -----------------------------------------------------------------------
    score_demanda = (
        0.40 * n_peatones    # flujo real de personas
        + 0.30 * n_transito  # accesibilidad
        + 0.20 * n_poblacion # tamaño del mercado potencial
        + 0.10 * n_turismo   # demanda turística
    )

    # SCORE RIESGO: supervivencia y saturación del epígrafe
    score_riesgo = (
        0.60 * n_supervivencia        # historial de negocios en la zona
        + 0.40 * (1.0 - n_competencia) # menos saturación = menos riesgo
    )

    # SCORE ATRACTOR: solo turismo y airbnb (sin tránsito)
    score_atractor = 0.50 * n_turismo + 0.50 * n_vut

    # -----------------------------------------------------------------------
    # SCORE ROBUSTO (corregido)
    # Antes: tránsito contado 3 veces, pesos solapados
    # Ahora: cada señal aparece una sola vez, pesos claros
    # -----------------------------------------------------------------------
    w_transito      = np.clip(importancia_transito / 100.0, 0.0, 1.0)
    w_supervivencia = np.clip(tolerancia_supervivencia / 100.0, 0.0, 1.0)

    score_robusto = (
        0.40 * score_demanda                         # demanda de mercado
        + 0.30 * w_supervivencia * score_riesgo      # riesgo ponderado por slider
        + 0.20 * w_transito * n_transito             # tránsito ponderado por slider
        + 0.10 * score_atractor                      # atractores externos
    )
    # Empuje explícito al perfil de marcha (la multiplicativa sola queda ahogada por otros términos)
    if horario_objetivo == "Ocio Nocturno / Tarde":
        score_robusto = score_robusto + 0.22 * n_nocturnidad_barrio
    elif horario_objetivo == "Diurno / Estándar":
        score_robusto = score_robusto + 0.22 * (1.0 - n_nocturnidad_barrio)

    # -----------------------------------------------------------------------
    # COMPONENTE MULTIPLICATIVA: bonus demográficos
    # -----------------------------------------------------------------------
    score_multiplicativo = (
        (score_base + bonus_terr + bonus_eco)
        / comp_ajustada
        * bonus_edad
        * bonus_genero
        * bonus_renta
        * bonus_horario
    )

    # -----------------------------------------------------------------------
    # BLEND FINAL
    # -----------------------------------------------------------------------
    base_blend = (
        0.55 * _safe_norm(score_multiplicativo)
        + 0.45 * score_robusto
    )

    # -----------------------------------------------------------------------
    # CAPA ML (corregido)
    # Antes: bonus_ml = 1.0 - 0.06 * tanh(residual)  → oscilaba ±6%, invisible
    # Ahora: bonus_ml = 1.0 - 0.20 * tanh(residual)  → oscila ±20%, visible
    # residual > 0: más oferta observada de la esperada → penalización suave
    # residual < 0: menos oferta de la esperada → bonus suave (posible hueco)
    # -----------------------------------------------------------------------
    ml_preds = _load_market_density_preds()
    bonus_ml = pd.Series(1.0, index=ranking.index)

    if ml_preds is not None and not ml_preds.empty:
        sub = ml_preds.loc[
            ml_preds["desc_epigrafe"] == epigrafe_objetivo,
            ["desc_barrio_local", "pred_log1p_n_locales"],
        ]
        sub = sub.drop_duplicates(subset=["desc_barrio_local"], keep="first")
        ranking = ranking.merge(sub, on="desc_barrio_local", how="left")
        bonus_ml = pd.Series(1.0, index=ranking.index)
        obs_log = np.log1p(ranking["competencia_directa"].astype(float))
        residual = obs_log - ranking["pred_log1p_n_locales"]
        mask = ranking["pred_log1p_n_locales"].notna()
        bonus_ml.loc[mask] = 1.0 - 0.20 * np.tanh(residual.loc[mask].astype(float))
        ranking.drop(columns=["pred_log1p_n_locales"], inplace=True, errors="ignore")

    ranking["score_inversion"] = base_blend * bonus_ml

    # Normalizar a 0-100
    max_val = ranking["score_inversion"].max()
    if max_val > 0:
        ranking["score_inversion"] = (ranking["score_inversion"] / max_val) * 100

    ranking = ranking.sort_values(by="score_inversion", ascending=False)

    columnas_return = [
        "desc_barrio_local",
        "score_inversion",
        "competencia_directa",
        "renta_neta_hogares",
        "locales_totales",
        "precio_m2_alquiler",
        "coste_alquiler_estimado",
        "tasa_supervivencia",
        "porcentaje_mujeres",
        "pension_media",
        "score_turismo",
        "score_transito",
        "peatones",
        "UNIDADES_VUT",
        "poblacion_total",
    ]
    salida = ranking[columnas_return].copy()
    return salida.head(5)