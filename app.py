import streamlit as st
import pandas as pd
from src.features.recommender import generar_ranking_barrios
from util_text import generar_texto_analista

st.set_page_config(page_title='Analista de Inversiones - Madrid', layout='wide')
st.title('Inteligencia Inmobiliaria y Comercial (Madrid) V4')
st.caption('Asistente Avanzado potenciado con Datos Empíricos Reales de Turismo y Aforo Peatonal')

@st.cache_data
def cargar_datos():
    return pd.read_csv('data/processed/negocios_scored.csv')

df = cargar_datos()

if 'analizado' not in st.session_state:
    st.session_state['analizado'] = False
if 'resultados' not in st.session_state:
    st.session_state['resultados'] = pd.DataFrame()

with st.sidebar.form('filtros_analisis'):
    st.header('Segmentación Target')
    epigrafe = st.selectbox('Sector del Negocio', df['desc_epigrafe'].dropna().unique())
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
    importancia_turismo = st.slider('Influencia del Turismo (Airbnbs)', 0.0, 100.0, 50.0, help='Priorizar zonas con alta carga de viviendas de uso turístico.')
    importancia_transito = st.slider('Importancia del Flujo Peatonal', 0.0, 100.0, 50.0, help='Priorizar barrios con el mayor aforo peatonal validado en sensores.')

    submitted = st.form_submit_button('Ejecutar Análisis Espacial ')

if submitted:
    st.session_state['analizado'] = True
    st.session_state['resultados'] = generar_ranking_barrios(
        df=df,
        epigrafe_objetivo=epigrafe,
        perfil_renta=perfil_renta,
        target_edad=target_edad,
        genero_objetivo=genero_objetivo,
        horario_objetivo=horario_objetivo,
        metros_cuadrados=metros_cuadrados,
        presupuesto_max=presupuesto_max,
        importancia_turismo=importancia_turismo,
        importancia_transito=importancia_transito
    )

import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium

if st.session_state['analizado']:
    resultados = st.session_state['resultados']
    if resultados is None or resultados.empty:
        st.error('Ningún barrio de Madrid cumple con estas estrictas condiciones. Prueba a aumentar tu Presupuesto Mensual Máximo o relajar otros criterios.')
    else:
        st.success(f'Análisis completado. Listando las {len(resultados)} zonas más atractivas...')
        
        col1, col2 = st.columns([1, 1])

        with col1:
            for rank_idx, (i, row) in enumerate(resultados.iterrows(), 1):
                with st.expander(f"Ranking #{rank_idx}: Barrio de {row['desc_barrio_local']} (Puntuación: {row['score_inversion']:.1f}/100)", expanded=(rank_idx==1)):
                    st.markdown(generar_texto_analista(row, epigrafe, metros_cuadrados))

        with col2:
            st.subheader('Mapa de Densidad Comercial')
            top_barrios = resultados['desc_barrio_local'].tolist()
            df_mapa = df[(df['desc_barrio_local'].isin(top_barrios)) & (df['desc_epigrafe'] == epigrafe)]
            
            if not df_mapa.empty and 'lat' in df_mapa.columns and 'lon' in df_mapa.columns:
                df_mapa = df_mapa.dropna(subset=['lat', 'lon'])
                if not df_mapa.empty:
                    # Comenzar con una vista general de todo Madrid, sin aproximar dinámicamente al centro del dato
                    m = folium.Map(location=[40.4168, -3.7038], zoom_start=11)
                    heat_data = df_mapa[['lat', 'lon']].values.tolist()
                    HeatMap(heat_data, radius=15).add_to(m)
                    
                    st_folium(m, width=600, height=500)
                else:
                    st.info('Los competidores no tienen coordenadas mapeables conocidas.')
            else:
                st.info('Este sector opera en modo Océano Azul en las zonas recomendadas: no existe competencia ubicable.')
