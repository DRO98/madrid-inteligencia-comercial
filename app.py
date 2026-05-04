import random

import pandas as pd
import streamlit as st
from src.features.recommender import (
    MIN_LOCALES_EPIGRAFE_MADRID,
    conteos_locales_por_epigrafe_madrid,
    generar_ranking_barrios,
    lista_epigrafes_con_soporte,
)
from util_text import generar_texto_analista

st.set_page_config(page_title='Analista de Inversiones - Madrid', layout='wide')


def _ensure_session_state() -> None:
    """Inicializa claves de la app; llamar tras set_page_config y antes de leer resultados."""
    if 'analizado' not in st.session_state:
        st.session_state['analizado'] = False
    if 'resultados' not in st.session_state:
        st.session_state['resultados'] = pd.DataFrame()
    if 'ctx_epigrafe' not in st.session_state:
        st.session_state['ctx_epigrafe'] = None
    if 'ctx_metros' not in st.session_state:
        st.session_state['ctx_metros'] = None


_ensure_session_state()

st.title('Inteligencia Inmobiliaria y Comercial (Madrid) V4')
st.caption('Asistente Avanzado potenciado con Datos Empíricos Reales de Turismo y Aforo Peatonal')

@st.cache_data
def cargar_datos():
    return pd.read_csv('data/processed/negocios_scored.csv')

df = cargar_datos()
conteos_epigrafe_madrid = conteos_locales_por_epigrafe_madrid(df)
epigrafes_disponibles = lista_epigrafes_con_soporte(df, MIN_LOCALES_EPIGRAFE_MADRID)


def _etiqueta_sector_con_conteo(epi: str) -> str:
    n = int(conteos_epigrafe_madrid.get(epi, 0))
    return f"{epi} ({n} locales en Madrid)"

_ensure_session_state()

with st.sidebar.form('filtros_analisis'):
    st.header('Segmentación Target')
    if not epigrafes_disponibles:
        st.warning(
            f'No hay sectores que cumplan el mínimo de **{MIN_LOCALES_EPIGRAFE_MADRID}** locales '
            'censados distintos en Madrid. Revisa el dataset o baja el umbral en `MIN_LOCALES_EPIGRAFE_MADRID`.'
        )
        epigrafe = ''
    else:
        epigrafe = st.selectbox(
            'Sector del Negocio',
            epigrafes_disponibles,
            format_func=_etiqueta_sector_con_conteo,
            key='sector_epigrafe_min_locales',
            help=(
                f'Solo aparecen sectores con ≥ {MIN_LOCALES_EPIGRAFE_MADRID} locales distintos '
                'en todo Madrid (censo); el número entre paréntesis es ese recuento.'
            ),
        )
    metros_cuadrados = st.number_input('M2 del Local Deseado', min_value=20, max_value=2000, value=100)
    presupuesto_max = st.number_input('Presupuesto Mensual Max (€)', min_value=500, max_value=50000, value=3500)
    
    st.markdown('---')
    st.subheader('Demografía Múltiple')
    perfil_renta = st.selectbox('Clase Social', ['Cualquiera', 'Barrios de Alta Renta (Premium)', 'Barrios de Renta Media/Baja (Volumen)'])
    target_edad = st.selectbox('Segmentos de Edad', ['Todos', 'Estudiantes y Gen Z (15-24 años)', 'Profesionales Jóvenes (25-39 años)', 'Familias / Edad Madura (40-64 años)', 'Seniors y Jubilados (65+ años)'])
    genero_objetivo = st.selectbox('Prevalencia de Género', ['Ambos', 'Hombres (Público Masculino)', 'Mujeres (Público Femenino)'])
    horario_objetivo = st.selectbox('Estilo de Ocio', ['Indiferente', 'Ocio Nocturno / Tarde', 'Diurno / Estándar'])

    st.markdown('---')
    st.subheader('¡NUEVO! Datos Empíricos')
    importancia_transito = st.slider('Importancia del Flujo Peatonal', 0.0, 100.0, 50.0, help='Priorizar barrios con el mayor aforo peatonal validado en sensores.')
    tolerancia_supervivencia = st.slider('Tolerancia Supervivencia Comercial', 0.0, 100.0, 50.0, help='Sube este valor para priorizar barrios donde los negocios sobreviven más.')

    submitted = st.form_submit_button('Ejecutar Análisis Espacial ')

_ensure_session_state()

if submitted and not epigrafes_disponibles:
    st.session_state['analizado'] = False
    st.error('No se puede ejecutar el análisis sin sectores con muestra suficiente.')
elif submitted:
    try:
        with st.spinner('Calculando ranking y señales por barrio (puede tardar unos segundos la primera vez)…'):
            out = generar_ranking_barrios(
                df=df,
                epigrafe_objetivo=epigrafe,
                perfil_renta=perfil_renta,
                target_edad=target_edad,
                genero_objetivo=genero_objetivo,
                horario_objetivo=horario_objetivo,
                metros_cuadrados=metros_cuadrados,
                presupuesto_max=presupuesto_max,
                importancia_transito=importancia_transito,
                tolerancia_supervivencia=tolerancia_supervivencia,
            )
        st.session_state['resultados'] = out
        st.session_state['analizado'] = True
        st.session_state['ctx_epigrafe'] = epigrafe
        st.session_state['ctx_metros'] = int(metros_cuadrados)
    except Exception as exc:
        st.session_state['analizado'] = False
        st.session_state['resultados'] = pd.DataFrame()
        st.error('Error al calcular el ranking. Detalle técnico:')
        st.exception(exc)

import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium

_ensure_session_state()

if st.session_state.get('analizado', False):
    resultados = st.session_state.get('resultados')
    if resultados is None:
        resultados = pd.DataFrame()
    ep_disp = st.session_state.get('ctx_epigrafe') or ''
    ctx_metros = st.session_state.get('ctx_metros')
    met_disp = ctx_metros if ctx_metros is not None else metros_cuadrados
    if resultados is None or resultados.empty:
        st.error('Ningún barrio de Madrid cumple con estas estrictas condiciones. Prueba a aumentar tu Presupuesto Mensual Máximo o relajar otros criterios.')
    else:
        st.success(f'Análisis completado. Listando las {len(resultados)} zonas más atractivas...')
        
        col1, col2 = st.columns([1, 1])

        with col1:
            for rank_idx, (i, row) in enumerate(resultados.iterrows(), 1):
                with st.expander(
                    f"Ranking #{rank_idx}: Barrio de {row['desc_barrio_local']} (Puntuación: {row['score_inversion']:.1f}/100)",
                    expanded=(rank_idx <= 3),
                ):
                    st.markdown(generar_texto_analista(row, ep_disp, met_disp))

        with col2:
            st.subheader('Mapa de Densidad Comercial')
            # Misma ejecución que el ranking (evita desync si cambias el selector después)
            df_mapa = df[df['desc_epigrafe'] == ep_disp].copy() if ep_disp else pd.DataFrame()
            if not df_mapa.empty and 'lat' in df_mapa.columns and 'lon' in df_mapa.columns:
                df_mapa = df_mapa.dropna(subset=['lat', 'lon'])
                # Excluir coords (0,0) y valores fuera del municipio (p. ej. locales agrupados mal geocodificados)
                df_mapa = df_mapa[
                    df_mapa['lat'].between(40.28, 40.58)
                    & df_mapa['lon'].between(-3.95, -3.52)
                ]
                # Un punto por local censado (evita duplicar calor si hay varias filas por id_local)
                if 'id_local' in df_mapa.columns:
                    df_mapa = df_mapa.drop_duplicates(subset=['id_local'], keep='first')
                n_locales_sector = int(df.loc[df['desc_epigrafe'] == ep_disp, 'id_local'].nunique())
                n_mapa = len(df_mapa)
                max_puntos_calor = 4000
                st.caption(
                    f'Calor con **{n_mapa}** ubicaciones distintas (`id_local`) dentro de Madrid; '
                    f'el sector tiene **{n_locales_sector}** locales censados en total. '
                    f'Si hay más de {max_puntos_calor} puntos, el mapa muestrea aleatoriamente para no bloquear el navegador.'
                )
                if n_mapa > 0:
                    m = folium.Map(location=[40.4168, -3.7038], zoom_start=11)
                    heat_data = df_mapa[['lat', 'lon']].values.tolist()
                    if len(heat_data) > max_puntos_calor:
                        rng = random.Random(42)
                        heat_data = rng.sample(heat_data, max_puntos_calor)
                    HeatMap(heat_data, radius=12, blur=15, max_zoom=13).add_to(m)
                    st_folium(m, use_container_width=True, height=480)
                else:
                    st.info(
                        'No hay coordenadas válidas para este sector en el dataset (o todas quedan fuera del bbox de Madrid).'
                    )
            else:
                st.info('No hay datos de mapa para este epígrafe (columnas lat/lon ausentes o tabla vacía).')
