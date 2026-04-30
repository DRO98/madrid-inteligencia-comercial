"""
Búsqueda de locales comerciales en venta en Madrid
usando el cliente unofficial de la API de Idealista:
  https://github.com/yagueto/idealista-api

Requisitos:
    pip install git+https://github.com/yagueto/idealista-api.git
    (o clona el repo y haz: pip install .)

Variables de entorno necesarias:
    IDEALISTA_API_KEY    → tu API Key de Idealista
    IDEALISTA_API_SECRET → tu API Secret de Idealista

Puedes obtener las credenciales en:
    https://developers.idealista.com/
"""

import os
import json
import csv
from idealista_api import Idealista, Search

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────

API_KEY    = os.getenv("IDEALISTA_API_KEY")
API_SECRET = os.getenv("IDEALISTA_API_SECRET")

# Location IDs de Madrid:
#   "0-EU-ES-28-07" → Madrid ciudad
#   "0-EU-ES-28"    → Comunidad de Madrid completa
LOCATION_ID = "0-EU-ES-28-07"

# Filtros de búsqueda (todos opcionales salvo los marcados como requeridos)
FILTROS = {
    "location_id":     LOCATION_ID,    # requerido
    "property_type":   "premises",     # locales comerciales
    "operation":       "sale",         # en venta
    "max_items":       50,             # máx. por página (límite API: 50)
    # Filtros adicionales opcionales:
    # "min_price":     50_000,
    # "max_price":     500_000,
    # "min_size":      50,             # m²
    # "max_size":      300,            # m²
}

# ─── LÓGICA PRINCIPAL ─────────────────────────────────────────────────────────

def obtener_todos_los_locales():
    """Pagina automáticamente por todos los resultados disponibles."""
    if not API_KEY or not API_SECRET:
        raise ValueError(
            "Faltan las variables de entorno IDEALISTA_API_KEY y/o IDEALISTA_API_SECRET.\n"
            "Ejemplo: export IDEALISTA_API_KEY='tu_key'"
        )

    idealista = Idealista(api_key=API_KEY, api_secret=API_SECRET)
    todos_los_locales = []
    pagina_actual = 1

    print(f"🔍 Buscando locales en venta en Madrid ({LOCATION_ID})...\n")

    while True:
        request = Search(
            "es",
            num_page=pagina_actual,
            **FILTROS,
        )

        response = idealista.query(request)

        print(f"  Página {response.page}/{response.total_pages} "
              f"— {len(response.element_list)} locales obtenidos "
              f"(total anunciados: {response.total})")

        todos_los_locales.extend(response.element_list)

        if pagina_actual >= response.total_pages:
            break
        pagina_actual += 1

    return todos_los_locales


def mostrar_resumen(locales):
    """Imprime un resumen legible de cada local."""
    print(f"\n{'═'*60}")
    print(f"  TOTAL DE LOCALES ENCONTRADOS: {len(locales)}")
    print(f"{'═'*60}\n")

    for i, local in enumerate(locales, 1):
        precio    = getattr(local, "price", "N/D")
        tamanyo   = getattr(local, "size", "N/D")
        direccion = getattr(local, "address", "N/D")
        distrito  = getattr(local, "district", "")
        url       = getattr(local, "url", "")
        desc      = getattr(local, "description", "")[:120]

        print(f"[{i:>3}] {direccion} ({distrito})")
        print(f"      Precio: {precio:,.0f} €  |  Tamaño: {tamanyo} m²")
        if url:
            print(f"      🔗 {url}")
        if desc:
            print(f"      {desc}...")
        print()


def exportar_a_csv(locales, ruta_csv="locales_madrid.csv"):
    """Exporta los locales a un CSV para análisis posterior."""
    if not locales:
        print("No hay locales para exportar.")
        return

    # Obtener todos los campos disponibles del primer elemento
    campos = [attr for attr in dir(locales[0])
              if not attr.startswith("_") and not callable(getattr(locales[0], attr))]

    with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for local in locales:
            fila = {campo: getattr(local, campo, "") for campo in campos}
            writer.writerow(fila)

    print(f"✅ Datos exportados a: {ruta_csv}")


def exportar_a_json(locales, ruta_json="locales_madrid.json"):
    """Exporta los locales a JSON."""
    if not locales:
        print("No hay locales para exportar.")
        return

    datos = []
    for local in locales:
        campos = {attr: getattr(local, attr, None)
                  for attr in dir(local)
                  if not attr.startswith("_") and not callable(getattr(local, attr))}
        datos.append(campos)

    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2, default=str)

    print(f"✅ Datos exportados a: {ruta_json}")


# ─── PUNTO DE ENTRADA ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    locales = obtener_todos_los_locales()

    mostrar_resumen(locales)

    # Exportar resultados
    exportar_a_csv(locales, "locales_madrid.csv")
    exportar_a_json(locales, "locales_madrid.json")