import pandas as pd
import numpy as np
import re
from pathlib import Path

def process_socioeconomico_data(input_path: str, output_path: str):
    """
    Procesa el archivo Excel de datos socioeconómicos de Madrid.
    Extrae la información a nivel ciudad, distrito y barrio.
    """
    print(f"Leyendo archivo: {input_path}")
    xls = pd.ExcelFile(input_path)
    
    # Filtrar solo las hojas que comienzan con "XX." (ej: "01. Centro")
    sheet_names = [sheet for sheet in xls.sheet_names if re.match(r"^\d{2}\.", sheet)]
    
    all_data = []
    
    for sheet in sheet_names:
        print(f"Procesando hoja: {sheet}")
        # Obtener el nombre limpio del distrito (ej "01. Centro" -> "Centro")
        distrito_name = sheet.split('.', 1)[1].strip()
        
        # Leer la hoja sin cabecera para manejarla manualmente por las celdas fusionadas
        df = xls.parse(sheet, header=None)
        
        # Fila 1: Nombres de los ámbitos (Ciudad, Distrito, Barrios...)
        row_headers = df.iloc[1].values
        
        # Extraer nombres de barrios (columnas con índice par >= 6)
        barrios_cols = {}
        for col_idx in range(6, len(df.columns), 2):
            barrio_val = row_headers[col_idx]
            if pd.notna(barrio_val) and str(barrio_val).strip() != "":
                # Limpiar el nombre del barrio (ej: "121. Orcasitas" -> "Orcasitas")
                clean_barrio = str(barrio_val).split('.', 1)[-1].strip() if '.' in str(barrio_val) else str(barrio_val).strip()
                barrios_cols[col_idx] = clean_barrio
                
        # Iterar desde la fila 2 en adelante para recoger indicadores
        for row_idx in range(2, len(df)):
            indicador = df.iloc[row_idx, 1]
            
            # Si no hay indicador válido, saltar fila
            if pd.isna(indicador) or str(indicador).strip() == "":
                continue
                
            indicador = str(indicador).strip()
            
            # Valor Ciudad de Madrid (índice 2)
            val_ciudad = df.iloc[row_idx, 2]
            if not pd.isna(val_ciudad):
                all_data.append({
                    'ambito': 'Ciudad de Madrid',
                    'tipo_ambito': 'ciudad',
                    'distrito': np.nan,  # A nivel ciudad el distrito es nulo
                    'indicador': indicador,
                    'valor': val_ciudad
                })
                
            # Valor Distrito (índice 4)
            val_distrito = df.iloc[row_idx, 4]
            if not pd.isna(val_distrito):
                all_data.append({
                    'ambito': distrito_name,
                    'tipo_ambito': 'distrito',
                    'distrito': distrito_name,
                    'indicador': indicador,
                    'valor': val_distrito
                })
                
            # Valores por Barrio (índices pares desde el 4)
            for col_idx, barrio_name in barrios_cols.items():
                val_barrio = df.iloc[row_idx, col_idx]
                if not pd.isna(val_barrio):
                    all_data.append({
                        'ambito': barrio_name,
                        'tipo_ambito': 'barrio',
                        'distrito': distrito_name,
                        'indicador': indicador,
                        'valor': val_barrio
                    })
                    
    # Construir DataFrame final
    df_final = pd.DataFrame(all_data)
    
    # Al procesar múltiples distritos, la info de la ciudad se duplicará.
    # Eliminamos duplicados para mantener solo una instancia por cada indicador a nivel 'ciudad'
    df_final = df_final.drop_duplicates(subset=['ambito', 'tipo_ambito', 'distrito', 'indicador'])
    
    # Crear carpeta de destino si no existe
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Guardar
    df_final.to_csv(out_path, index=False)
    print(f"\nProceso completado. Datos guardados en: {out_path}")
    print(f"Total de registros: {len(df_final)}")

if __name__ == "__main__":
    input_file = "data/socioeconomico.xlsx"
    output_file = "data/socioeconomico_limpio.csv"
    process_socioeconomico_data(input_file, output_file)
