"""
Modelo complementario: densidad de mercado esperada (barrio × epígrafe).

Target: log1p(n_locales) con n_locales = id_local distintos por par.
Entrenamiento con GroupKFold por barrio para métricas honestas; modelo final
sobre todo el dataset para exportar predicciones al recomendador.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

try:
    import lightgbm as lgb
    from sklearn.model_selection import GroupKFold
except ImportError:  # entorno sin ML instalado
    lgb = None  # type: ignore
    GroupKFold = None  # type: ignore

# Columnas usadas como contexto barrio (primera fila por barrio en el censo)
_BAR_FEATURES = [
    "renta_neta_hogares",
    "precio_m2_real",
    "poblacion_total",
    "tasa_supervivencia_real",
    "tasa_paro",
    "pct_extranjeros",
    "densidad_poblacion",
    "score_transito",
    "score_turismo",
]

_COMBO_MEANS = ["es_nocturno", "capacidad_exterior", "terraza_acondicionada"]


def build_training_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (barrio, epígrafe) con target y features."""
    df = df.copy()
    if "capacidad_exterior" not in df.columns and "capacidad_exterior_total" in df.columns:
        df = df.rename(columns={"capacidad_exterior_total": "capacidad_exterior"})

    gcols = ["desc_barrio_local", "desc_epigrafe"]
    agg_dict: dict[str, str] = {"id_local": "nunique"}
    for c in _COMBO_MEANS:
        if c in df.columns:
            agg_dict[c] = "mean"
    combo = df.groupby(gcols, as_index=False).agg(agg_dict)
    combo.rename(columns={"id_local": "n_locales"}, inplace=True)

    first_cols = [c for c in _BAR_FEATURES if c in df.columns]
    barrio_first = (
        df.sort_values("id_local")
        .groupby("desc_barrio_local", as_index=False)[first_cols]
        .first()
    )
    out = combo.merge(barrio_first, on="desc_barrio_local", how="left")

    vut_col = "UNIDADES_VUT"
    if vut_col in df.columns:
        vmean = df.groupby("desc_barrio_local")[vut_col].mean().reset_index()
        vmean.rename(columns={vut_col: "unidades_vut_media_barrio"}, inplace=True)
        out = out.merge(vmean, on="desc_barrio_local", how="left")

    out["target_log1p"] = np.log1p(out["n_locales"].astype(float))
    return out


def _prepare_feature_matrix(df_train: pd.DataFrame) -> pd.DataFrame:
    feature_cols = [
        c
        for c in df_train.columns
        if c not in ("desc_barrio_local", "n_locales", "target_log1p")
    ]
    X = df_train[feature_cols].copy()
    if "desc_epigrafe" in X.columns:
        X["desc_epigrafe"] = X["desc_epigrafe"].astype("category")
    cat_cols = [c for c in X.columns if str(X[c].dtype.name) == "category"]
    num_cols = [c for c in X.columns if c not in cat_cols]
    return pd.concat([X[num_cols], X[cat_cols]], axis=1)


def train_market_density_model(
    df_train: pd.DataFrame,
    *,
    n_splits: int = 5,
    random_state: int = 42,
) -> tuple["lgb.Booster", dict[str, float]]:
    """CV por barrio y entrena booster final. Devuelve (modelo, métricas CV)."""
    if lgb is None or GroupKFold is None:
        raise ImportError("Instala lightgbm y scikit-learn: pip install lightgbm scikit-learn")

    X = _prepare_feature_matrix(df_train)
    y = df_train["target_log1p"].values
    groups = df_train["desc_barrio_local"].values

    params = {
        "objective": "regression",
        "metric": "rmse",
        "verbosity": -1,
        "boosting_type": "gbdt",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "max_depth": 8,
        "min_data_in_leaf": 80,
        "feature_fraction": 0.85,
        "bagging_fraction": 0.85,
        "bagging_freq": 1,
        "seed": random_state,
    }

    gkf = GroupKFold(n_splits=n_splits)
    rmse_folds: list[float] = []

    for fold_idx, (tr_idx, va_idx) in enumerate(gkf.split(X, y, groups)):
        X_tr, X_va = X.iloc[tr_idx], X.iloc[va_idx]
        y_tr, y_va = y[tr_idx], y[va_idx]
        dtr = lgb.Dataset(X_tr, label=y_tr)
        dva = lgb.Dataset(X_va, label=y_va, reference=dtr)
        booster = lgb.train(
            params,
            dtr,
            num_boost_round=600,
            valid_sets=[dva],
            callbacks=[lgb.early_stopping(80, verbose=False)],
        )
        pred = booster.predict(X_va, num_iteration=booster.best_iteration)
        rmse = float(np.sqrt(np.mean((pred - y_va) ** 2)))
        rmse_folds.append(rmse)

    metrics = {
        "cv_rmse_mean": float(np.mean(rmse_folds)),
        "cv_rmse_std": float(np.std(rmse_folds)),
    }

    dfull = lgb.Dataset(X, label=y)
    final = lgb.train(params, dfull, num_boost_round=450)
    return final, metrics


def export_predictions_csv(
    df_raw: pd.DataFrame,
    booster: "lgb.Booster",
    out_csv: Path | str,
) -> pd.DataFrame:
    df_train = build_training_frame(df_raw)
    X = _prepare_feature_matrix(df_train)

    pred = booster.predict(X)
    out = pd.DataFrame(
        {
            "desc_barrio_local": df_train["desc_barrio_local"],
            "desc_epigrafe": df_train["desc_epigrafe"],
            "n_locales": df_train["n_locales"],
            "pred_log1p_n_locales": pred,
        }
    )
    out_path = Path(out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    return out


def train_and_export_default_paths(
    csv_in: Path | str | None = None,
    model_out: Path | str | None = None,
    pred_csv_out: Path | str | None = None,
) -> dict[str, float]:
    """Entrena y guarda modelo + CSV de predicciones (rutas por defecto desde raíz repo)."""
    root = Path(__file__).resolve().parents[2]
    csv_in = Path(csv_in or root / "data" / "processed" / "negocios_scored.csv")
    model_out = Path(model_out or root / "models" / "lgbm_market_density.txt")
    pred_csv_out = Path(pred_csv_out or root / "data" / "processed" / "market_density_lgbm.csv")

    df_raw = pd.read_csv(csv_in)
    df_train = build_training_frame(df_raw)
    booster, metrics = train_market_density_model(df_train)
    model_out.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(model_out))
    export_predictions_csv(df_raw, booster, pred_csv_out)
    return metrics


if __name__ == "__main__":
    m = train_and_export_default_paths()
    print("CV RMSE (log1p): mean=", m["cv_rmse_mean"], "std=", m["cv_rmse_std"])
    print("Modelo y predicciones exportados.")
