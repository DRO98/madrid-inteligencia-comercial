import random
import re

import folium
import pandas as pd
import streamlit as st
from branca.element import Element
from folium.plugins import HeatMap
from streamlit_folium import st_folium

from negocios import (
    MIN_LOCALES_EPIGRAFE_MADRID,
    PERFIL_RENTA_LABEL,
    PUBLICO_LABEL_Y_SCORE,
    conteos_locales_por_epigrafe_madrid,
    ficha_local_html,
    lista_epigrafes_con_soporte,
    negocios_scored,
    popup_marcador_streamlit_html,
    preparar_tabla_negocios,
)

st.set_page_config(page_title="Analista de Inversiones - Madrid", layout="wide")

_BUSCAR_ICON_HTML = (
    '<div style="font-size:22px;line-height:28px;width:28px;height:28px;text-align:center;'
    'text-shadow:0 1px 3px rgba(0,0,0,.45);">🔍</div>'
)


def _folium_icon_buscar() -> folium.DivIcon:
    return folium.DivIcon(
        html=_BUSCAR_ICON_HTML,
        icon_size=(28, 28),
        icon_anchor=(14, 14),
        popup_anchor=(0, -12),
        class_name="marker-buscar-local",
    )


def _folium_sin_fondo_iconos(mapa: folium.Map) -> None:
    mapa.get_root().header.add_child(
        Element(
            "<style>"
            ".marker-buscar-local.leaflet-marker-icon,"
            ".marker-buscar-local.leaflet-div-icon{"
            "background:transparent!important;border:none!important;}"
            ".popup-map-mini{font-size:13px;line-height:1.45;max-width:260px;padding:2px 0;}"
            ".popup-map-mini-epi{opacity:.88;font-size:12px;margin-top:4px;}"
            ".popup-map-mini-hint{opacity:.72;font-size:11px;margin-top:6px;}"
            "</style>"
        )
    )


def _indice_marcador_desde_popup(raw: object | None) -> int | None:
    if raw is None:
        return None
    s = str(raw)
    m = re.search(r'data-midx="(\d+)"', s)
    if m:
        return int(m.group(1))
    m = re.search(r"data-midx=&quot;(\d+)&quot;", s)
    return int(m.group(1)) if m else None


def _indice_marcador_desde_click(
    click_obj: object | None,
    coords_por_ix: list[tuple[int, float, float]],
    tol_grados: float = 5e-6,
) -> int | None:
    """Fallback robusto: resuelve fila por coordenadas del marcador clicado."""
    if not isinstance(click_obj, dict):
        return None
    lat = click_obj.get("lat")
    lon = click_obj.get("lng", click_obj.get("lon"))
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None
    best_ix: int | None = None
    best_d = float("inf")
    for ix, mlat, mlon in coords_por_ix:
        d = abs(mlat - lat_f) + abs(mlon - lon_f)
        if d < best_d:
            best_d = d
            best_ix = ix
    if best_ix is None or best_d > tol_grados:
        return None
    return best_ix


def _ensure_session_state() -> None:
    if "analizado" not in st.session_state:
        st.session_state["analizado"] = False
    if "salida_negocios" not in st.session_state:
        st.session_state["salida_negocios"] = None
    if "panel_local_marcador_ix" not in st.session_state:
        st.session_state["panel_local_marcador_ix"] = None


_ensure_session_state()

st.title("Inteligencia Inmobiliaria y Comercial (Madrid)")
st.caption(
    "Ranking de locales (`negocios.py`): varios públicos (media de scores de censo), renta, presupuesto dinámico, "
    "competencia local, tránsito y atractivo. Índices y costes por candidato en los popups del Mapa 1."
)
st.markdown(
    """
<style>
.stApp {
    background: #f5f7fb;
    color: #1f2937;
}
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] li {
    font-size: 1.02rem;
    line-height: 1.6;
}
[data-testid="stMarkdownContainer"] h3 {
    font-size: 1.9rem;
    line-height: 1.2;
    margin-top: .45rem;
    color: #1e3a5f;
}
.stAlert {
    border-radius: 12px;
}
.streamlit-local-ficha {
    font-size: 1.02rem;
    line-height: 1.6;
}
.streamlit-local-ficha .local-ficha-inner {
    border: 1px solid #d7dee8;
    border-radius: 14px;
    padding: 1rem 1.1rem;
    background: #ffffff;
    box-shadow: 0 8px 20px rgba(30, 58, 95, 0.08);
}
.streamlit-local-ficha .ficha-titulo {
    margin: 0 0 .7rem;
    font-size: 1.02rem;
    color: #0f2742;
}
.streamlit-local-ficha .ficha-line {
    margin: .5rem 0;
    font-size: .98rem;
}
.streamlit-local-ficha .ficha-etiq {
    opacity: .78;
    font-size: .8rem;
    text-transform: uppercase;
    letter-spacing: .045em;
    color: #415a77;
}
.streamlit-local-ficha .ficha-sub {
    opacity: .82;
    font-size: .9rem;
}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data
def cargar_datos() -> pd.DataFrame:
    df_raw = pd.read_csv("data/processed/negocios_scored.csv")
    return preparar_tabla_negocios(df_raw)


df = cargar_datos()
conteos_epigrafe_madrid = conteos_locales_por_epigrafe_madrid(df)
epigrafes_disponibles = lista_epigrafes_con_soporte(df, MIN_LOCALES_EPIGRAFE_MADRID)


def _etiqueta_sector_con_conteo(epi: str) -> str:
    n = int(conteos_epigrafe_madrid.get(epi, 0))
    return f"{epi} ({n} locales en Madrid)"


_ensure_session_state()

_publico_keys = list(PUBLICO_LABEL_Y_SCORE.keys())
_publico_etiqueta = {k: PUBLICO_LABEL_Y_SCORE[k][0] for k in _publico_keys}
_perfil_keys = list(PERFIL_RENTA_LABEL.keys())

with st.sidebar.form("filtros_negocios"):
    st.header("Filtros")
    if not epigrafes_disponibles:
        st.warning(
            f"No hay sectores con al menos **{MIN_LOCALES_EPIGRAFE_MADRID}** locales "
            "distintos en Madrid (censo)."
        )
        epigrafe = ""
    else:
        epigrafe = st.selectbox(
            "Tipo de negocio (epígrafe)",
            epigrafes_disponibles,
            format_func=_etiqueta_sector_con_conteo,
            help="Actividad censada en Madrid Open Data.",
        )
    publico_objetivo = st.multiselect(
        "Público / edad objetivo (elige uno o varios)",
        options=_publico_keys,
        default=["millennial"],
        format_func=lambda k: _publico_etiqueta[k],
        help="Se usa la media de los scores de censo seleccionados (filtro μ−σ y ranking demográfico).",
    )
    perfil_renta = st.selectbox(
        "Perfil renta (zona)",
        options=_perfil_keys,
        format_func=lambda k: PERFIL_RENTA_LABEL[k],
    )
    presupuesto = st.number_input(
        "Presupuesto mensual objetivo (€)",
        min_value=500,
        max_value=50000,
        value=3500,
        help="Banda de coste estimado alrededor de este importe: semiancho dinámico (p. ej. 500 €→±200 €, 10 000 €→±2500 €).",
    )
    metros_cuadrados = st.number_input("Superficie deseada (m²)", min_value=20, max_value=2000, value=100)

    submitted = st.form_submit_button("Buscar locales")

_ensure_session_state()

if submitted and not epigrafes_disponibles:
    st.session_state["analizado"] = False
    st.session_state["salida_negocios"] = None
    st.error("No hay sectores disponibles.")
elif submitted:
    if not publico_objetivo:
        st.error("Selecciona al menos un segmento de edad / público objetivo.")
    else:
        try:
            with st.spinner("Filtrando locales…"):
                out = negocios_scored(
                    df,
                    tipo_negocio=epigrafe,
                    publico_objetivo=publico_objetivo,
                    presupuesto=float(presupuesto),
                    metros_requeridos=float(metros_cuadrados),
                    perfil_renta=perfil_renta,
                )
            st.session_state["salida_negocios"] = out
            st.session_state["analizado"] = True
            st.session_state["panel_local_marcador_ix"] = None
            st.session_state["ctx_epigrafe"] = epigrafe
            st.session_state["ctx_publico"] = list(publico_objetivo)
            st.session_state["ctx_perfil_renta"] = perfil_renta
            st.session_state["ctx_metros"] = int(metros_cuadrados)
            st.session_state["ctx_presupuesto"] = float(presupuesto)
        except Exception as exc:
            st.session_state["analizado"] = False
            st.session_state["salida_negocios"] = None
            st.error("Error al ejecutar la búsqueda.")
            st.exception(exc)

_ensure_session_state()

if st.session_state.get("analizado") and st.session_state.get("salida_negocios"):
    salida = st.session_state["salida_negocios"]
    locales: pd.DataFrame = salida["locales"]
    barrios: list = salida["barrios"]
    ep_disp = st.session_state.get("ctx_epigrafe") or ""

    meta = salida.get("meta") or {}
    if locales is None or locales.empty:
        st.warning(
            "Ningún local cumple los filtros (demografía, renta, presupuesto, coste). "
            "Prueba a relajar perfil de renta o el presupuesto."
        )
    else:
        m_pb = meta.get("margen_presupuesto", "—")
        st.success(
            f"**{len(locales)}** mejores locales por **índice global** (percentil en el conjunto filtrado; top 20). "
            f"Barrios: **{', '.join(barrios)}**. Banda presupuesto ±**{m_pb}** €. "
            "Pulsa una lupa 🔍 en el mapa: la ficha completa se muestra en el **panel al lado**."
        )

        # --- Mapa 1: candidatos ---
        st.markdown("### Tus locales destacados en la ciudad")
        st.markdown(
            "Cada **lupa** 🔍 marca un sitio que encaja con tu sector, público y presupuesto. "
            "En el mapa solo verás un resumen; **la ficha detallada aparece al lado** al hacer clic."
        )
        m_reco = folium.Map(location=[40.4168, -3.7038], zoom_start=12)
        _folium_sin_fondo_iconos(m_reco)
        icon_buscar = _folium_icon_buscar()
        puntos_validos: list[tuple[float, float]] = []
        filas_en_mapa: list[pd.Series] = []
        coords_por_ix: list[tuple[int, float, float]] = []
        for _, row in locales.iterrows():
            lat, lon = row.get("lat"), row.get("lon")
            if pd.isna(lat) or pd.isna(lon):
                continue
            lat_f, lon_f = float(lat), float(lon)
            if not (40.28 <= lat_f <= 40.58 and -3.95 <= lon_f <= -3.52):
                continue
            puntos_validos.append((lat_f, lon_f))
            ix_m = len(filas_en_mapa)
            filas_en_mapa.append(row)
            coords_por_ix.append((ix_m, lat_f, lon_f))
            bar_txt = str(row.get("desc_barrio_local", "") or "")[:72]
            folium.Marker(
                [lat_f, lon_f],
                icon=icon_buscar,
                popup=folium.Popup(
                    popup_marcador_streamlit_html(row, ix_m),
                    max_width=280,
                ),
                tooltip=f"🔍 {bar_txt}" if bar_txt else "🔍 Ver ficha al lado",
            ).add_to(m_reco)
        n_marcadores = len(filas_en_mapa)
        if puntos_validos:
            if len(puntos_validos) == 1:
                m_reco.location = list(puntos_validos[0])
                m_reco.zoom_start = 15
            else:
                lats = [p[0] for p in puntos_validos]
                lons = [p[1] for p in puntos_validos]
                m_reco.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], padding=(24, 24))
            st.caption(
                f"**{n_marcadores}** ubicaciones en el mapa. Clic en una lupa para cargar la ficha en el panel."
            )
            col_mapa, col_ficha = st.columns([1.45, 1])
            with col_mapa:
                out_map = st_folium(m_reco, width=None, height=440, key="mapa_locales_reco")
            if out_map:
                ix_click = _indice_marcador_desde_popup(out_map.get("last_object_clicked_popup"))
                if ix_click is None:
                    ix_click = _indice_marcador_desde_click(
                        out_map.get("last_object_clicked"),
                        coords_por_ix,
                    )
                if ix_click is not None:
                    st.session_state["panel_local_marcador_ix"] = ix_click
            with col_ficha:
                ix_sel = st.session_state.get("panel_local_marcador_ix")
                if ix_sel is not None and 0 <= ix_sel < len(filas_en_mapa):
                    st.markdown(
                        '<div class="streamlit-local-ficha">'
                        + ficha_local_html(filas_en_mapa[ix_sel])
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption(
                        "Haz clic en una **lupa** del mapa para ver aquí superficie, alquiler orientativo "
                        "y el resto de datos sin tapar el plano."
                    )
        else:
            st.info(
                "Hay locales candidatos pero sin coordenadas válidas en Madrid para pintar marcadores."
            )

    # --- Mapa 2: calor sector ---
    st.markdown("### Dónde está de verdad tu sector en Madrid")
    st.markdown(
        "Aquí no es un ranking: muestra **dónde hay más locales como el tuyo** según el censo. "
        "Las zonas más calientes son donde esa actividad está más concentrada; las claras, donde hay menos. "
        "Te ayuda a situarte: ¿vas a un barrio muy cargado de tu mismo tipo de negocio o a uno con menos competencia directa?"
    )
    df_mapa = df[df["desc_epigrafe"] == ep_disp].copy() if ep_disp else pd.DataFrame()
    if not df_mapa.empty and "lat" in df_mapa.columns and "lon" in df_mapa.columns:
        df_mapa = df_mapa.dropna(subset=["lat", "lon"])
        df_mapa = df_mapa[
            df_mapa["lat"].between(40.28, 40.58) & df_mapa["lon"].between(-3.95, -3.52)
        ]
        if "id_local" in df_mapa.columns:
            df_mapa = df_mapa.drop_duplicates(subset=["id_local"], keep="first")
        n_locales_sector = int(df.loc[df["desc_epigrafe"] == ep_disp, "id_local"].nunique())
        max_puntos_calor = 4000
        heat_data = df_mapa[["lat", "lon"]].values.tolist()
        n_ubicaciones = len(heat_data)
        if n_ubicaciones > max_puntos_calor:
            rng = random.Random(42)
            heat_data = rng.sample(heat_data, max_puntos_calor)
        n_mostrados = len(heat_data)
        if n_ubicaciones > max_puntos_calor:
            st.caption(
                f"En Madrid hay **{n_locales_sector}** locales de este tipo registrados; "
                f"podemos situar **{n_ubicaciones}** en el mapa. Para que no se quede colgado el navegador, "
                f"aquí ves **{n_mostrados}** puntos elegidos al azar entre todos."
            )
        else:
            st.caption(
                f"En Madrid hay **{n_locales_sector}** locales de este tipo registrados; "
                f"este mapa muestra **{n_mostrados}** ubicaciones donde aparecen en el censo."
            )
        if n_ubicaciones > 0:
            m_heat = folium.Map(location=[40.4168, -3.7038], zoom_start=11)
            HeatMap(heat_data, radius=12, blur=15, max_zoom=13).add_to(m_heat)
            st_folium(m_heat, width=None, height=480, key="mapa_calor_sector")
        else:
            st.info("No hay ubicaciones con coordenadas para dibujar este mapa.")
    else:
        st.info("No hay datos de ubicación para este sector en la tabla.")
