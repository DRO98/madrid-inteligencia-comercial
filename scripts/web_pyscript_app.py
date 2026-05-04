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
