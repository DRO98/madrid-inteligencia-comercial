# Inteligencia Inmobiliaria y Comercial (Madrid)

Aplicación de análisis para localizar oportunidades de local comercial en Madrid, basada en datos públicos y un motor de scoring propio en `negocios.py`.

El proyecto tiene dos interfaces:
- `app.py` (Streamlit)
- `docs/` (web estática para GitHub Pages con PyScript + Leaflet)

## Qué hace hoy

- Filtra por sector (`epígrafe`), presupuesto, perfil de renta y público objetivo (multi-selección).
- Calcula un ranking de candidatos con señales de:
  - demografía
  - competencia cercana
  - tránsito
  - atractivo urbano (turismo, VUT, población, peatones)
- Muestra:
  - Mapa 1: locales candidatos (marcadores + ficha de detalle)
  - Mapa 2: densidad real del sector en Madrid (heatmap)
- Incluye m² sintéticos por local (`metros_local_sintetico`) para estimar alquiler mensual orientativo hasta integrar una fuente inmobiliaria directa.

## Motor principal

- Archivo central: `negocios.py`
- Función principal: `negocios_scored(...)`
- Dataset de entrada local: `data/processed/negocios_scored.csv`

## Estructura del repositorio

- `app.py`: interfaz Streamlit.
- `negocios.py`: lógica de scoring, filtros, métricas y popups/fichas.
- `scripts/web_pyscript_app.py`: lógica UI de la web estática.
- `scripts/build_github_pages.py`: genera `docs/main.py` y `docs/data/negocios_web.csv.gz`.
- `docs/index.html`, `docs/static/app.css`: frontend estático.
- `notebooks/`: ETL y preparación de datos.

## Instalación (local)

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Ejecución

### Streamlit

```bash
streamlit run app.py
```

### Web estática (GitHub Pages / local)

1) Regenerar artefactos:

```bash
python scripts/build_github_pages.py
```

2) Probar local:

```bash
cd docs
python -m http.server 8000
```

Abrir `http://localhost:8000/`.

## Fuentes de datos (alto nivel)

- Censo de locales y actividades (Madrid Open Data)
- Aforos peatonales
- Viviendas de uso turístico (VUT)
- Padrón y variables sociodemográficas
- Renta e indicadores económicos por zona
- Precio de alquiler por m²

## Estado actual

- El proyecto **ya no utiliza** `src/features/recommender.py`.
- Toda la lógica activa de recomendación vive en `negocios.py`.
