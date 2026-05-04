# -*- coding: utf-8 -*-
# Generado por scripts/build_github_pages.py — no editar.

from __future__ import annotations

"""
Señal de nocturnidad.

`actividades.tsv` solo cubre una fracción pequeña del censo de locales; la mayoría
no tiene `hora_cierre1`. Por eso combinamos el indicador derivado del horario con
un proxy por epígrafe (locales típicamente nocturnos por definición).

La lista de subcadenas es deliberadamente conservadora para limitar falsos positivos.
"""

import re

import pandas as pd

# Subcadenas en MAYÚSCULAS tal como suelen venir en `desc_epigrafe` (después de .upper()).
EPIGRAFE_SUBCADENAS_NOCTURNAS: tuple[str, ...] = (
    "PUB",
    "DISCOTECA",
    "SALA DE FIESTAS",
    "BAR ESPECIAL",
    "CAFE CONCIERTO",
    "CAFÉ CONCIERTO",
    "SALA DE BAILE",
    "TABERNA",
)


def epigrafe_indica_nocturnidad(desc_epigrafe: str | float | None) -> float:
    """1.0 si el texto del epígrafe sugiere uso nocturno típico; 0.0 si no."""
    if desc_epigrafe is None or (isinstance(desc_epigrafe, float) and pd.isna(desc_epigrafe)):
        return 0.0
    u = str(desc_epigrafe).upper()
    return 1.0 if any(s in u for s in EPIGRAFE_SUBCADENAS_NOCTURNAS) else 0.0


def serie_nocturno_por_epigrafe(desc_epigrafes: pd.Series) -> pd.Series:
    """Misma regla que `epigrafe_indica_nocturnidad`, vectorizada (substring segura)."""
    u = desc_epigrafes.fillna("").astype(str).str.upper()
    mask = pd.Series(False, index=u.index)
    for s in EPIGRAFE_SUBCADENAS_NOCTURNAS:
        mask = mask | u.str.contains(re.escape(s), regex=True, na=False)
    return mask.astype(float)

def generar_texto_analista(row, epigrafe, metros_cuadrados):
    # Determinar viabilidad
    if row['score_inversion'] >= 85:
        viabilidad = "muy alta"
    elif row['score_inversion'] >= 65:
        viabilidad = "alta"
    else:
        viabilidad = "media-alta"
        
    # Tipo de concepto
    if row['score_turismo'] > 60 and row['score_transito'] > 60:
        concepto = f"{epigrafe.lower()} de alto flujo turístico y tracción peatonal continua"
    elif row['score_turismo'] > 50:
        concepto = f"{epigrafe.lower()} turístico o semi-premium enfocado a visitantes"
    elif row['score_transito'] > 50:
        concepto = f"{epigrafe.lower()} de alto flujo peatonal y rotación"
    elif row['renta_neta_hogares'] > 45000:
        concepto = f"{epigrafe.lower()} de destino, boutique o premium enfocado a residentes locales"
    else:
        concepto = f"{epigrafe.lower()} urbano, informal, con fuerte tracción de público local"
        
    # Riesgo (basado en coste alquiler, competencia y supervivencia)
    if row['coste_alquiler_estimado'] > 4000 and row['tasa_supervivencia'] < 65:
        riesgo = "alto (costes fijos elevados y alta mortalidad de negocios)"
    elif row['coste_alquiler_estimado'] > 3000 or row['competencia_directa'] > 15:
        riesgo = "medio-alto (exige buena ejecución operativa por alquiler o competencia)"
    else:
        riesgo = "medio (equilibrio aceptable de barreras de entrada)"
        
    # Motivos
    motivos = []
    if row['score_transito'] > 60:
        motivos.append("tráfico peatonal altísimo")
    if row['score_turismo'] > 60:
        motivos.append("fuerte presión turística")
    if row['renta_neta_hogares'] > 50000:
        motivos.append("renta residente excepcional")
    if row['competencia_directa'] > 20:
        motivos.append(f"mercado muy activo con amplia oferta")
    if row['tasa_supervivencia'] > 80:
        motivos.append("alta fidelización comercial")
        
    if not motivos:
        motivo_str = "identidad fuerte, actividad estable y buenas condiciones base."
    else:
        motivo_str = " y ".join([", ".join(motivos[:-1]), motivos[-1]] if len(motivos) > 1 else motivos) + "."

    # Formateo de puntuaciones extra
    turismo_text = f"Nivel {row['score_turismo']:.1f}/100 de concentración en el distrito" if row['score_turismo'] > 0 else "Frecuencia turística no significativa o dato no disponible"
    transito_text = f"Nivel {row['score_transito']:.1f}/100 de aglomeración registrada por sensores" if row['score_transito'] > 0 else "Tránsito moderado o sensor peatonal no disponible"
    
    # Redondeamos o aproximamos valores exactos para no dar falsa precisión
    renta_aprox = round(row['renta_neta_hogares'] / 1000) * 1000
    pension_aprox = round(row['pension_media'] / 100) * 100
    supervivencia_aprox = round(row['tasa_supervivencia'] / 5) * 5

    return f"""
*Conclusiones del Analista:*
- **Viabilidad comercial:** {viabilidad}.
- **Tipo de concepto recomendado:** {concepto}.
- **Riesgo:** {riesgo}.
- **Motivo principal:** {motivo_str}

---
**Estimaciones Matemáticas del Modelo:**
* Coste de alquiler estimado en la zona: **~{row['precio_m2_alquiler']:.0f} €/m²**.
* Coste de local comercial aproximado mensual: **~{row['coste_alquiler_estimado']:,.0f} €**
* Proporción de género predictiva: **~{row['porcentaje_mujeres']:.0f}% Público Femenino**.

**Datos Empíricos del INE (Aproximaciones Generales):**
* Renta Neta Media de Hogares general: **entorno a {renta_aprox:,.0f} €**
* Tasa de Supervivencia Comercial: **sobre el {supervivencia_aprox}%**.
* Economía Senior: Pensión media en la zona de **~{pension_aprox:,.0f} €**.

**Señales Reales de Actividad y Presión Espacial:**
* **Ocupación Turística (Airbnbs VUT):** {turismo_text}.
* **Flujo Peatonal Medio:** {transito_text}.
"""

import numpy as np
import pandas as pd

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

    sub_epi = df.loc[df["desc_epigrafe"] == epigrafe_objetivo].dropna(
        subset=["desc_barrio_local", "id_local"]
    )
    comp = (
        sub_epi.groupby("desc_barrio_local", observed=False)["id_local"]
        .nunique()
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

    # Capa ML (predicciones LGBM densidad esperada por barrio×epígrafe) retirada: el modelo subestima
    # fuerte los mercados densos en escala natural (ej. residual positivo medio ~6 locales cuando n≥10),
    # forzando penalización repetida sobre barrios muy competidos. El score usa solo datos observados.

    ranking["score_inversion"] = base_blend

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

# Fragmento concatenado tras nocturnidad + util_text + recommender (ver build_github_pages.py).

import asyncio
import html as html_lib
import io
import json
import random
import re

import pandas as pd
from js import updateHeatmap
from pyodide.http import pyfetch
from pyscript import document, web, when

_df: pd.DataFrame | None = None
_epigrafes: list[str] = []
_conteos: dict[str, int] = {}
_load_lock: asyncio.Lock | None = None


def _analista_html(mdish: str) -> str:
    t = html_lib.escape(mdish)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return t.replace("\n", "<br/>")


async def ensure_data_loaded() -> None:
    """Descarga gzip una vez y rellena el selector de sectores."""
    global _df, _epigrafes, _conteos, _load_lock

    if _load_lock is None:
        _load_lock = asyncio.Lock()

    async with _load_lock:
        status = web.page["status-msg"]
        if _df is not None:
            return

        status.innerHTML = "<span>Cargando Pyodide…</span>"
        resp = await pyfetch("data/negocios_web.csv.gz")
        raw = await resp.bytes()
        status.innerHTML = "<span>Parseando tabla (~146k filas, CPU intensivo)</span>"
        loop = asyncio.get_event_loop()
        _df = await loop.run_in_executor(
            None, lambda: pd.read_csv(io.BytesIO(raw), compression="gzip")
        )

        cnt = conteos_locales_por_epigrafe_madrid(_df)
        _conteos = {str(k): int(v) for k, v in cnt.items()}
        _epigrafes = lista_epigrafes_con_soporte(_df, MIN_LOCALES_EPIGRAFE_MADRID)

        sel = web.page["epigrafe"]
        sel.innerHTML = ""
        if not _epigrafes:
            opt = document.createElement("option")
            opt.value = ""
            opt.innerText = f"Sin sectores (mínimo {MIN_LOCALES_EPIGRAFE_MADRID} locales)"
            sel.appendChild(opt)
            status.innerHTML = "<strong>No hay epígrafes con muestra suficiente.</strong>"
            return

        for ep in _epigrafes:
            n = int(_conteos.get(ep, 0))
            opt = document.createElement("option")
            opt.value = ep
            opt.innerText = f"{ep} ({n} locales en Madrid)"
            sel.appendChild(opt)

        status.innerHTML = (
            "<strong>Listo.</strong> Ajusta filtros y pulsa <em>Ejecutar análisis</em>."
        )


def _start_run(_event=None):
    asyncio.create_task(_run_analysis())


@when("click", "#btn-run")
def on_run_click(_event=None):
    _start_run(_event)


async def _run_analysis():
    err = web.page["err-msg"]
    err.innerHTML = ""
    await ensure_data_loaded()

    assert _df is not None

    ep = web.page["epigrafe"].value
    if not ep:
        err.innerHTML = "Selecciona un sector válido."
        return

    metros = int(web.page["metros"].value or 100)
    presupuesto = float(web.page["presupuesto"].value or 3500)
    perfil_renta = web.page["perfil_renta"].value
    target_edad = web.page["target_edad"].value
    genero_objetivo = web.page["genero_objetivo"].value
    horario_objetivo = web.page["horario_objetivo"].value
    importancia_transito = float(web.page["importancia_transito"].value or 50)
    tolerancia_supervivencia = float(web.page["tolerancia_supervivencia"].value or 50)

    res_cards = web.page["results-cards"]
    map_cap = web.page["map-caption"]
    res_cards.innerHTML = "<p>Calculando ranking…</p>"
    map_cap.innerText = ""

    loop = asyncio.get_event_loop()

    def work():
        return generar_ranking_barrios(
            df=_df,
            epigrafe_objetivo=ep,
            perfil_renta=perfil_renta,
            target_edad=target_edad,
            genero_objetivo=genero_objetivo,
            horario_objetivo=horario_objetivo,
            metros_cuadrados=metros,
            presupuesto_max=presupuesto,
            importancia_transito=importancia_transito,
            tolerancia_supervivencia=tolerancia_supervivencia,
        )

    try:
        out = await loop.run_in_executor(None, work)
    except Exception as exc:  # pragma: no cover
        err.innerHTML = html_lib.escape(f"Error: {exc!r}")
        res_cards.innerHTML = ""
        return

    if out.empty:
        res_cards.innerHTML = (
            "<p class=\"warn\">Ningún barrio cumple los criterios. "
            "Sube presupuesto o relaja filtros.</p>"
        )
        updateHeatmap(json.dumps([]))
        return

    head = (
        "<p class=\"ok\">Ranking generado. "
        f"Sector <strong>{html_lib.escape(ep)}</strong>; m²: {metros}.</p>"
    )
    ranks: list[str] = []
    for rank_idx, (_, row) in enumerate(out.iterrows(), 1):
        title = (
            f"#{rank_idx} · {html_lib.escape(str(row['desc_barrio_local']))} "
            f"— score {float(row['score_inversion']):.1f}/100"
        )
        expanded = " open" if rank_idx <= 3 else ""
        body = _analista_html(generar_texto_analista(row, ep, metros))
        ranks.append(
            f"<details class=\"rank\"{expanded}><summary>{title}</summary><div>{body}</div></details>"
        )

    max_pts = 4000
    df_m = _df[_df["desc_epigrafe"] == ep].dropna(subset=["lat", "lon"])
    df_m = df_m[
        (df_m["lat"].between(40.28, 40.58)) & (df_m["lon"].between(-3.95, -3.52))
    ]
    if "id_local" in df_m.columns:
        df_m = df_m.drop_duplicates(subset=["id_local"], keep="first")
    coords = df_m[["lat", "lon"]].values.tolist()
    if len(coords) > max_pts:
        rng = random.Random(42)
        coords = rng.sample(coords, max_pts)
    n_sector = int(_df.loc[_df["desc_epigrafe"] == ep, "id_local"].nunique())
    map_cap.innerHTML = html_lib.escape(
        f"Puntos calor: {len(coords)} (máx. {max_pts}). Locales censados únicos sector: {n_sector}."
    )

    res_cards.innerHTML = head + "".join(ranks)
    updateHeatmap(json.dumps(coords))


async def boot():
    try:
        await ensure_data_loaded()
    except Exception as exc:  # pragma: no cover
        web.page["status-msg"].innerHTML = html_lib.escape(
            f"No se pudieron cargar los datos ({exc}). Revisa que sirves desde http.server/GitHub Pages (no file://)."
        )


asyncio.ensure_future(boot())
