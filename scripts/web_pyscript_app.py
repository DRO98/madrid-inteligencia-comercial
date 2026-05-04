# Fragmento concatenado tras negocios.py (ver scripts/build_github_pages.py).

import asyncio
import html as html_lib
import io
import json
import random

import pandas as pd
from js import updateHeatmap, updateRecoMarkers
from pyodide.http import pyfetch
from pyscript import document, web, when

_df: pd.DataFrame | None = None
_epigrafes: list[str] = []
_conteos: dict[str, int] = {}
_load_lock: asyncio.Lock | None = None


async def ensure_data_loaded() -> None:
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
        status.innerHTML = "<span>Parseando tabla y estimando m² por local…</span>"
        loop = asyncio.get_event_loop()
        raw_local = raw

        def _load_and_prep() -> pd.DataFrame:
            raw_df = pd.read_csv(io.BytesIO(raw_local), compression="gzip")
            return preparar_tabla_negocios(raw_df)

        _df = await loop.run_in_executor(None, _load_and_prep)

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
            opt.innerText = f"{ep} ({n} locales)"
            sel.appendChild(opt)

        status.innerHTML = (
            "<strong>Listo.</strong> Sigue los pasos del asistente; en el último pulsa "
            "<em>Analizar y ver mapas</em>."
        )


def _start_run(_event=None):
    asyncio.create_task(_run_analysis())


@when("click", "#btn-run")
def on_run_click(_event=None):
    _start_run(_event)


def _publicos_seleccionados() -> list[str]:
    sel = document.querySelectorAll('input[name="publico_obj"]:checked')
    n = int(sel.length)
    return [str(sel.item(i).value) for i in range(n)]


async def _run_analysis():
    err = web.page["err-msg"]
    err.innerHTML = ""
    await ensure_data_loaded()

    assert _df is not None

    ep = web.page["epigrafe"].value
    if not ep:
        err.innerHTML = "Selecciona un sector válido."
        return

    metros = float(web.page["metros"].value or 100)
    presupuesto = float(web.page["presupuesto"].value or 3500)
    publicos = _publicos_seleccionados()
    perfil = web.page["perfil_renta"].value

    if not publicos:
        err.innerHTML = "Selecciona al menos un público objetivo."
        return

    res_cards = web.page["results-cards"]
    cap_reco = web.page["map-reco-caption"]
    cap_heat = web.page["map-heat-caption"]
    res_cards.innerHTML = "<p>Buscando…</p>"
    cap_reco.innerText = ""
    cap_heat.innerText = ""

    loop = asyncio.get_event_loop()

    def work():
        return negocios_scored(
            _df,
            tipo_negocio=ep,
            publico_objetivo=publicos,
            presupuesto=presupuesto,
            metros_requeridos=metros,
            perfil_renta=perfil,
        )

    try:
        salida = await loop.run_in_executor(None, work)
    except Exception as exc:  # pragma: no cover
        err.innerHTML = html_lib.escape(f"Error: {exc!r}")
        res_cards.innerHTML = ""
        updateRecoMarkers(json.dumps([]))
        updateHeatmap(json.dumps([]))
        return

    locales = salida["locales"]

    if locales is None or locales.empty:
        res_cards.innerHTML = (
            "<p class=\"warn\">Ningún local cumple los filtros. "
            "Prueba otro público o presupuesto.</p>"
        )
        updateRecoMarkers(json.dumps([]))
    else:
        res_cards.innerHTML = ""

        markers: list[dict] = []
        for _, row in locales.iterrows():
            lat, lon = row.get("lat"), row.get("lon")
            if pd.isna(lat) or pd.isna(lon):
                continue
            lat_f, lon_f = float(lat), float(lon)
            if not (40.28 <= lat_f <= 40.58 and -3.95 <= lon_f <= -3.52):
                continue
            markers.append(
                {
                    "lat": lat_f,
                    "lon": lon_f,
                    "popup_mini": popup_mapa_breve_html(row),
                    "detail_html": ficha_local_html(row),
                }
            )
        cap_reco.innerHTML = "<p class=\"cap muted\">" + html_lib.escape(
            f"En esta búsqueda hay {len(markers)} ubicaciones en Madrid. Pulsa una lupa 🔍: la ficha completa se muestra en el panel junto al mapa."
        ) + "</p>"
        updateRecoMarkers(json.dumps(markers))

    max_pts = 4000
    df_m = _df[_df["desc_epigrafe"] == ep].dropna(subset=["lat", "lon"])
    df_m = df_m[
        (df_m["lat"].between(40.28, 40.58)) & (df_m["lon"].between(-3.95, -3.52))
    ]
    if "id_local" in df_m.columns:
        df_m = df_m.drop_duplicates(subset=["id_local"], keep="first")
    coords = df_m[["lat", "lon"]].values.tolist()
    n_ubicaciones = len(coords)
    if len(coords) > max_pts:
        rng = random.Random(42)
        coords = rng.sample(coords, max_pts)
    n_mostrados = len(coords)
    n_sector = int(_df.loc[_df["desc_epigrafe"] == ep, "id_local"].nunique())
    if n_ubicaciones > max_pts:
        cap_txt = (
            f"En Madrid hay {n_sector} locales de este tipo registrados; podemos situar {n_ubicaciones} en el mapa. "
            f"Para que cargue bien, aquí ves {n_mostrados} puntos elegidos al azar entre todos."
        )
    else:
        cap_txt = (
            f"En Madrid hay {n_sector} locales de este tipo registrados; "
            f"este mapa muestra {n_mostrados} ubicaciones donde aparecen en el censo."
        )
    cap_heat.innerHTML = "<p class=\"cap muted\">" + html_lib.escape(cap_txt) + "</p>"
    updateHeatmap(json.dumps(coords))
    try:
        import js

        js.revealMapResults()
    except Exception:
        pass


async def boot():
    try:
        await ensure_data_loaded()
    except Exception as exc:  # pragma: no cover
        web.page["status-msg"].innerHTML = html_lib.escape(
            f"No se pudieron cargar datos ({exc}). Usa http.server, no file://."
        )


asyncio.ensure_future(boot())
