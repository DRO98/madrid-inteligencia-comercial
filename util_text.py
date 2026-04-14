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
