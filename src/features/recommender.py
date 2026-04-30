import pandas as pd
import numpy as np

def generar_ranking_barrios(
    df: pd.DataFrame, 
    epigrafe_objetivo: str, 
    peso_eco: float = 5.0, 
    peso_terraza: float = 5.0, 
    perfil_renta: str = 'Cualquiera', 
    target_edad: str = 'Todos', 
    genero_objetivo: str = 'Ambos',
    horario_objetivo: str = 'Indiferente', 
    metros_cuadrados: int = 100, 
    presupuesto_max: float = 3000.0,
    importancia_turismo: float = 50.0,
    importancia_transito: float = 50.0,
    tolerancia_supervivencia: float = 50.0
) -> pd.DataFrame:
    def _safe_norm(series: pd.Series) -> pd.Series:
        s = series.fillna(0.0).astype(float)
        max_v = s.max()
        min_v = s.min()
        if max_v <= min_v:
            return pd.Series(np.ones(len(s)), index=s.index)
        return (s - min_v) / (max_v - min_v)

    aggs = {
        'id_local': 'count',          
        'es_nocturno': 'mean',
        'capacidad_exterior': 'mean',
        'terraza_acondicionada': 'mean',
        'score_joven_real': 'first',     
        'score_millennial_real': 'first',
        'score_familiar_real': 'first',
        'score_senior_real': 'first',
        'renta_neta_hogares': 'first', 
        'score_turismo': 'first',
        'score_transito': 'first',
        'peatones': 'mean',
        'UNIDADES_VUT': 'mean',
        'poblacion_total': 'first',
        'precio_m2_real': 'first',
        'porcentaje_mujeres_real': 'first',
        'pension_media_real': 'first',
        'tasa_supervivencia_real': 'first'
    }
    
    barrios = df.groupby('desc_barrio_local').agg(aggs).reset_index()
    barrios.rename(columns={'id_local': 'locales_totales'}, inplace=True)
    
    # FILTRO: Para evitar sesgos
    barrios = barrios[barrios['locales_totales'] >= 15]
    
    comp = df[df['desc_epigrafe'] == epigrafe_objetivo].groupby('desc_barrio_local').size().reset_index(name='competencia_directa')
    ranking = pd.merge(barrios, comp, on='desc_barrio_local', how='left').fillna({'competencia_directa': 0})
    
    # --- CÁLCULO DE DATOS EXACTOS EN LUGAR DE PROXIES ---
    
    # Precio Alquiler (m2) usando datos reales del histórico y oferta
    # Empleamos 'precio_m2_real' generado por el ETL oficial de portales inmobiliarios
    ranking['precio_m2_alquiler'] = ranking['precio_m2_real']
    ranking['coste_alquiler_estimado'] = ranking['precio_m2_real'] * metros_cuadrados
    
    # Supervivencia de Negocios (Tasa de Éxito de un negocio en esa zona al 1er año)
    ranking['tasa_supervivencia'] = ranking['tasa_supervivencia_real'] * 100.0
    
    # Ratio Hombres / Mujeres (Dato Oficial del INE - Padrón)
    ranking['porcentaje_mujeres'] = ranking['porcentaje_mujeres_real']
    
    # Pensión Media (Para segmento Jubilado)
    ranking['pension_media'] = ranking['pension_media_real']
    ranking['score_competencia'] = np.log1p(ranking['competencia_directa'])

    # --- FILTRO EXCLUYENTE PRECIO ---
    ranking = ranking[ranking['coste_alquiler_estimado'] <= presupuesto_max]
    
    if ranking.empty:
        return pd.DataFrame()

    # --- CÁLCULO BASE INVERSORA ---
    score_base = (ranking['locales_totales'] / ranking['locales_totales'].max()) * 50
    comp_ajustada = np.log1p(ranking['competencia_directa']) + 1 

    bonus_terr = (ranking['capacidad_exterior'] / (ranking['capacidad_exterior'].max() + 0.1)) * peso_terraza * 5
    bonus_eco = (ranking['terraza_acondicionada'] / (ranking['terraza_acondicionada'].max() + 0.1)) * peso_eco * 5
    
    # --- BONUS EDAD: 4 SEGMENTOS DE NICHO USANDO PADRÓN REAL ---
    bonus_edad = 1.0 
    if target_edad == 'Estudiantes y Gen Z (15-24 años)':
        bonus_edad = ranking['score_joven_real'] / 20.0  
    elif target_edad == 'Profesionales Jóvenes (25-39 años)':
        bonus_edad = ranking['score_millennial_real'] / 20.0
    elif target_edad == 'Familias / Edad Madura (40-64 años)':
        bonus_edad = ranking['score_familiar_real'] / 20.0
    elif target_edad == 'Seniors y Jubilados (65+ años)':
        bonus_edad = (ranking['score_senior_real'] / 20.0) * (ranking['pension_media'] / 1200.0)


    # --- BONUS GÉNERO ---
    bonus_genero = 1.0
    if genero_objetivo == 'Mujeres (Público Femenino)':
        bonus_genero = ranking['porcentaje_mujeres'] / 50.0
    elif genero_objetivo == 'Hombres (Público Masculino)':
        bonus_genero = (100 - ranking['porcentaje_mujeres']) / 50.0

    # --- BONUS RENTA ---
    bonus_renta = 1.0 
    if perfil_renta == 'Barrios de Alta Renta (Premium)':
        bonus_renta = ranking['renta_neta_hogares'] / ranking['renta_neta_hogares'].max()
    elif perfil_renta == 'Barrios de Renta Media/Baja (Volumen)':
        bonus_renta = 1.0 - (ranking['renta_neta_hogares'] / ranking['renta_neta_hogares'].max())

    # --- BONUS HORARIO OCIO ---
    bonus_horario = 1.0 
    med_nocturno = ranking['es_nocturno'].median()
    if horario_objetivo == 'Ocio Nocturno / Tarde':
        bonus_horario = np.where(ranking['es_nocturno'] > med_nocturno, 1.2, 0.8) 
    elif horario_objetivo == 'Diurno / Estándar':
        bonus_horario = np.where(ranking['es_nocturno'] <= med_nocturno, 1.2, 0.8)

    # --- FORMULA FINAL V3 CON TODOS LOS BONUS ---
    # Incorporamos los datos empíricos de Aforo (Tránsito Peatonal) y Airbnb (Turismo)
    bonus_turismo = 1.0 + (ranking['score_turismo'].fillna(0) / 100.0) * (importancia_turismo / 50.0)
    bonus_transito = 1.0 + (ranking['score_transito'].fillna(0) / 100.0) * (importancia_transito / 50.0)

    # Componente multiplicativa original (afinidad de mercado)
    score_multiplicativo = ((score_base + bonus_terr + bonus_eco) / comp_ajustada) * bonus_edad * bonus_genero * bonus_renta * bonus_horario * bonus_turismo * bonus_transito

    # Componente aditiva robusta (evita que un único factor domine por multiplicación)
    w_transito = np.clip(importancia_transito / 100.0, 0.0, 1.0)
    w_supervivencia = np.clip(tolerancia_supervivencia / 100.0, 0.0, 1.0)

    n_transito = _safe_norm(ranking['score_transito'])
    n_turismo = _safe_norm(ranking['score_turismo'])
    n_supervivencia = _safe_norm(ranking['tasa_supervivencia'])
    n_poblacion = _safe_norm(ranking['poblacion_total'])
    n_vut = _safe_norm(ranking['UNIDADES_VUT'])
    n_peatones = _safe_norm(ranking['peatones'])
    n_competencia = _safe_norm(ranking['score_competencia'])

    score_demanda = (0.35 * n_transito) + (0.25 * n_peatones) + (0.20 * n_poblacion) + (0.20 * n_turismo)
    score_atractor = (0.5 * n_turismo) + (0.5 * n_vut)
    score_riesgo = (0.65 * n_supervivencia) + (0.35 * (1.0 - n_competencia))

    score_robusto = (
        0.35 * score_demanda
        + 0.15 * score_atractor
        + 0.25 * w_transito * n_transito
        + 0.25 * w_supervivencia * n_supervivencia
        + 0.15 * (1.0 - n_competencia)
    )

    # Blend final: se mantiene la lógica original y se suma una capa robusta orientada a decisión
    ranking['score_inversion'] = (0.55 * _safe_norm(score_multiplicativo)) + (0.45 * score_robusto)
    
    max_val = ranking['score_inversion'].max()
    if max_val > 0:
         ranking['score_inversion'] = (ranking['score_inversion'] / max_val) * 100

    ranking = ranking.sort_values(by='score_inversion', ascending=False)
    
    columnas_return = ['desc_barrio_local', 'score_inversion', 'competencia_directa', 'renta_neta_hogares', 'locales_totales', 'precio_m2_alquiler', 'coste_alquiler_estimado', 'tasa_supervivencia', 'porcentaje_mujeres', 'pension_media', 'score_turismo', 'score_transito', 'peatones', 'UNIDADES_VUT', 'poblacion_total']
    salida = ranking[columnas_return].copy()
    return salida.head(5)
