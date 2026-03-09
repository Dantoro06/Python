# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from motor.motor_multi_cuenta import ejecutar_motor_multicuenta
except Exception:
    from motor_multi_cuenta import ejecutar_motor_multicuenta

try:
    from motor_bonus_abuse import ejecutar as ejecutar_bonus_abuse_fn
except Exception:
    try:
        from motor.motor_bonus_abuse import ejecutar as ejecutar_bonus_abuse_fn
    except Exception:
        from .motor_bonus_abuse import ejecutar as ejecutar_bonus_abuse_fn

try:
    from motor.pipeline_contracts import normalizar_user_id
except Exception:
    from pipeline_contracts import normalizar_user_id


DEFAULT_CONFIG_BONUS_ABUSE: Dict = {
    "umbral_ratio_bono_deposito": 1.5,
    "umbral_horas_bono_retiro": 24,
    "umbral_cantidad_bonos": 3,
}


def _coerce_text(value):
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except Exception:
        pass
    return str(value)


def _resolver_cache_multicuenta(config: Optional[dict]) -> Optional[dict]:
    if not isinstance(config, dict):
        return None
    shared_runtime = config.get("_shared_runtime")
    if not isinstance(shared_runtime, dict):
        return None
    return shared_runtime


def _obtener_salidas_multicuenta(
    df_base: pd.DataFrame,
    config: Optional[dict] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    shared_runtime = _resolver_cache_multicuenta(config)
    if shared_runtime is not None and "multi_cuenta_outputs" in shared_runtime:
        return shared_runtime["multi_cuenta_outputs"]

    df_multi, df_self = ejecutar_motor_multicuenta(df_base.copy())
    if shared_runtime is not None:
        shared_runtime["multi_cuenta_outputs"] = (df_multi, df_self)
    return df_multi, df_self


def wrapper_multi_cuenta(
    df_base: pd.DataFrame,
    df_raw: Optional[pd.DataFrame] = None,
    df_bonos: Optional[pd.DataFrame] = None,
    config: Optional[dict] = None,
) -> pd.DataFrame:
    """
    Devuelve SOLO salida multiusuario (lista para normalizar al contrato).
    """
    if df_base is None or df_base.empty:
        return pd.DataFrame()

    df_multi, _ = _obtener_salidas_multicuenta(df_base, config=config)
    if df_multi is None or df_multi.empty:
        return pd.DataFrame()

    out = df_multi.copy()
    if "usuarios_implicados" in out.columns:
        out["user_id"] = out["usuarios_implicados"].astype(str).str.split("|")
        out = out.explode("user_id")
        out["user_id"] = out["user_id"].astype(str).str.strip()

    out["flags"] = "multi_cuenta"
    if "selecciones_por_usuario" in out.columns:
        out["evidencia"] = out["selecciones_por_usuario"].map(_coerce_text)
    if "nivel_riesgo" not in out.columns and "nivel_riesgo_multi" in out.columns:
        out["nivel_riesgo"] = out["nivel_riesgo_multi"]
    if "user_id" in out.columns:
        out["user_id"] = out["user_id"].map(normalizar_user_id)
    else:
        out["user_id"] = None
    return out


def wrapper_self_hedging(
    df_base: pd.DataFrame,
    df_raw: Optional[pd.DataFrame] = None,
    df_bonos: Optional[pd.DataFrame] = None,
    config: Optional[dict] = None,
) -> pd.DataFrame:
    """
    Devuelve SOLO salida self-hedging (lista para normalizar al contrato).
    """
    if df_base is None or df_base.empty:
        return pd.DataFrame()

    _, df_self = _obtener_salidas_multicuenta(df_base, config=config)
    if df_self is None or df_self.empty:
        return pd.DataFrame()

    out = df_self.copy()
    if "usuarios_implicados" in out.columns:
        out["user_id"] = out["usuarios_implicados"]

    out["flags"] = "self_hedging"
    if "selecciones_por_usuario" in out.columns:
        out["evidencia"] = out["selecciones_por_usuario"].map(_coerce_text)
    if "nivel_riesgo" not in out.columns and "nivel_riesgo_self" in out.columns:
        out["nivel_riesgo"] = out["nivel_riesgo_self"]
    if "user_id" in out.columns:
        out["user_id"] = out["user_id"].map(normalizar_user_id)
    else:
        out["user_id"] = None
    return out


def _resumir_bonus_abuse_por_usuario(df_bonus: pd.DataFrame) -> pd.DataFrame:
    if df_bonus is None or df_bonus.empty:
        return pd.DataFrame(
            columns=["user_id", "nivel_riesgo", "score", "flags", "evidencia"]
        )

    df = df_bonus.copy()
    if "nivel_riesgo_bonus" in df.columns and "nivel_riesgo" not in df.columns:
        df["nivel_riesgo"] = df["nivel_riesgo_bonus"]
    if "score_bonus_abuse" in df.columns and "score" not in df.columns:
        df["score"] = df["score_bonus_abuse"]

    for col in ["ratio_bono_deposito", "horas_bono_retiro", "cantidad_bonos"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    flag_cols = [
        c
        for c in ["flag_ratio_alto", "flag_retiro_rapido", "flag_frecuencia_alta"]
        if c in df.columns
    ]
    for c in flag_cols:
        df[c] = df[c].fillna(False).astype(bool)

    if "user_id" not in df.columns:
        df["user_id"] = None
    df["user_id"] = df["user_id"].map(normalizar_user_id)
    df = df[df["user_id"].notna()].copy()
    if df.empty:
        return pd.DataFrame(
            columns=["user_id", "nivel_riesgo", "score", "flags", "evidencia"]
        )

    prioridad = {"BAJO": 1, "MEDIO": 2, "ALTO": 3, "CRITICO": 4}
    df["nivel_riesgo"] = df["nivel_riesgo"].map(
        lambda x: None if pd.isna(x) else str(x).upper().strip()
    )
    df["_prio"] = df["nivel_riesgo"].map(prioridad).fillna(0).astype("int64")
    df["_score_num"] = pd.to_numeric(df["score"], errors="coerce").fillna(-1)

    df_ordenado = df.sort_values(
        ["user_id", "_prio", "_score_num"], ascending=[True, False, False]
    )
    nivel_user = (
        df_ordenado.groupby("user_id", as_index=False)
        .head(1)[["user_id", "nivel_riesgo"]]
        .reset_index(drop=True)
    )
    score_user = (
        df.groupby("user_id", as_index=False)["_score_num"]
        .max()
        .rename(columns={"_score_num": "score"})
    )

    if flag_cols:
        flags_user = df.groupby("user_id", as_index=False)[flag_cols].any()
        flags_user["flags"] = flags_user.apply(
            lambda row: "|".join(
                [c.replace("flag_", "") for c in flag_cols if bool(row[c])]
            )
            or "bonus_abuse",
            axis=1,
        )
        flags_user = flags_user[["user_id", "flags"]]
    else:
        flags_user = (
            df[["user_id"]]
            .drop_duplicates()
            .assign(flags="bonus_abuse")
            .reset_index(drop=True)
        )

    agg_dict = {}
    if "ratio_bono_deposito" in df.columns:
        agg_dict["ratio_max"] = ("ratio_bono_deposito", "max")
    if "horas_bono_retiro" in df.columns:
        agg_dict["horas_min"] = ("horas_bono_retiro", "min")
    if "cantidad_bonos" in df.columns:
        agg_dict["bonos_max"] = ("cantidad_bonos", "max")

    if agg_dict:
        evidencia_base = df.groupby("user_id", as_index=False).agg(**agg_dict)
    else:
        evidencia_base = df[["user_id"]].drop_duplicates().reset_index(drop=True)

    def _format_evidencia_row(row: pd.Series) -> str:
        partes = []
        ratio_max = row.get("ratio_max", np.nan)
        horas_min = row.get("horas_min", np.nan)
        cant_max = row.get("bonos_max", np.nan)
        if pd.notna(ratio_max):
            partes.append(f"ratio_max={round(float(ratio_max), 3)}")
        if pd.notna(horas_min):
            partes.append(f"horas_min={round(float(horas_min), 2)}")
        if pd.notna(cant_max):
            cant_val = float(cant_max)
            partes.append(
                f"bonos={int(cant_val)}"
                if cant_val.is_integer()
                else f"bonos={round(cant_val, 2)}"
            )
        return " | ".join(partes) if partes else "resumen_bonus_abuse"

    evidencia_base["evidencia"] = evidencia_base.apply(_format_evidencia_row, axis=1)
    evidencia_user = evidencia_base[["user_id", "evidencia"]]

    agg = nivel_user.merge(score_user, on="user_id", how="left")
    agg = agg.merge(flags_user, on="user_id", how="left")
    agg = agg.merge(evidencia_user, on="user_id", how="left")
    return agg[["user_id", "nivel_riesgo", "score", "flags", "evidencia"]]


def wrapper_bonus_abuse(
    df_base: Optional[pd.DataFrame] = None,
    df_raw: Optional[pd.DataFrame] = None,
    df_bonos: Optional[pd.DataFrame] = None,
    config: Optional[dict] = None,
) -> pd.DataFrame:
    """
    Ejecuta bonus abuse y devuelve 1 fila por user_id.
    """
    if df_raw is None or df_raw.empty:
        return pd.DataFrame()

    cfg = DEFAULT_CONFIG_BONUS_ABUSE.copy()
    if isinstance(config, dict):
        cfg.update(config)

    df_bonus, _metricas = ejecutar_bonus_abuse_fn(
        df_raw,
        pd.DataFrame(),
        df_bonos if df_bonos is not None else pd.DataFrame(),
        pd.DataFrame(),
        cfg,
    )
    return _resumir_bonus_abuse_por_usuario(df_bonus)
