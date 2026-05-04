"""
Señal de nocturnidad.

`actividades.tsv` solo cubre una fracción pequeña del censo de locales; la mayoría
no tiene `hora_cierre1`. Por eso combinamos el indicador derivado del horario con
un proxy por epígrafe (locales típicamente nocturnos por definición).

La lista de subcadenas es deliberadamente conservadora para limitar falsos positivos.
"""

from __future__ import annotations

import re

import pandas as pd

# Subcadenas en MAYÚSCULAS tal como suelen venir en `desc_epigrafe` (después de .upper()).
EPIGRAFE_SUBCADENAS_NOCTURNAS: tuple[str, ...] = (
    "PUB",
    "DISCOTECA",
    "SALA DE FIESTAS",
    "BAR ESPECIAL",
    "CAFE CONCIERTO",
    "CAFÉ CONCIERTO",
    "SALA DE BAILE",
    "TABERNA",
)


def epigrafe_indica_nocturnidad(desc_epigrafe: str | float | None) -> float:
    """1.0 si el texto del epígrafe sugiere uso nocturno típico; 0.0 si no."""
    if desc_epigrafe is None or (isinstance(desc_epigrafe, float) and pd.isna(desc_epigrafe)):
        return 0.0
    u = str(desc_epigrafe).upper()
    return 1.0 if any(s in u for s in EPIGRAFE_SUBCADENAS_NOCTURNAS) else 0.0


def serie_nocturno_por_epigrafe(desc_epigrafes: pd.Series) -> pd.Series:
    """Misma regla que `epigrafe_indica_nocturnidad`, vectorizada (substring segura)."""
    u = desc_epigrafes.fillna("").astype(str).str.upper()
    mask = pd.Series(False, index=u.index)
    for s in EPIGRAFE_SUBCADENAS_NOCTURNAS:
        mask = mask | u.str.contains(re.escape(s), regex=True, na=False)
    return mask.astype(float)
