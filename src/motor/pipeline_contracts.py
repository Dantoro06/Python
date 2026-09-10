# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

import pandas as pd


CONTRATO_COLUMNS = [
    "user_id",
    "motor",
    "nivel_riesgo",
    "score",
    "flags",
    "evidencia",
]

CONTRATO_DETALLE_COLUMNS = CONTRATO_COLUMNS + ["event_name", "fecha_bucket"]


PRIORIDAD_RIESGO = {
    "BAJO": 1,
    "MEDIO": 2,
    "ALTO": 3,
    "CRITICO": 4,
}


def _is_na(value) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _coerce_text(value) -> Optional[str]:
    if _is_na(value):
        return None
    return str(value)


def normalizar_user_id(value) -> Optional[str]:
    """
    Normaliza user_id a string estable para evitar 101 vs 101.0.
    """
    if _is_na(value):
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith(".0"):
        entero = s[:-2]
        if entero.isdigit():
            return entero
    return s


def normalizar_salida_motor(df: pd.DataFrame, motor_name: str) -> pd.DataFrame:
    """
    Normaliza una salida de motor al contrato de detalle:
    user_id, motor, nivel_riesgo, score, flags, evidencia,
    event_name y fecha_bucket (opcionales, nulos si no existen).
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=CONTRATO_DETALLE_COLUMNS)

    out = df.copy()
    out["motor"] = motor_name

    if "user_id" not in out.columns:
        out["user_id"] = None
    out["user_id"] = out["user_id"].map(normalizar_user_id)

    if "nivel_riesgo" not in out.columns:
        out["nivel_riesgo"] = None
    out["nivel_riesgo"] = out["nivel_riesgo"].map(
        lambda x: None if _is_na(x) else str(x).upper().strip()
    )

    if "score" not in out.columns:
        out["score"] = None
    if "flags" not in out.columns:
        out["flags"] = None
    if "evidencia" not in out.columns:
        out["evidencia"] = None

    out["flags"] = out["flags"].map(_coerce_text)
    out["evidencia"] = out["evidencia"].map(_coerce_text)
    for column in CONTRATO_DETALLE_COLUMNS:
        if column not in out.columns:
            out[column] = None
    return out[CONTRATO_DETALLE_COLUMNS]


def consolidar_riesgo_global(df_detalle: pd.DataFrame) -> pd.DataFrame:
    """
    Consolida detalle a 1 fila por user_id segun prioridad de riesgo.
    Prioridad: BAJO < MEDIO < ALTO < CRITICO.
    En empate, prioriza score mayor.
    """
    if df_detalle is None or df_detalle.empty:
        return pd.DataFrame(columns=CONTRATO_COLUMNS)

    df = df_detalle.copy()
    df = df[df["user_id"].notna()].copy()
    if df.empty:
        return pd.DataFrame(columns=CONTRATO_COLUMNS)

    df["_prioridad"] = (
        df["nivel_riesgo"].map(PRIORIDAD_RIESGO).fillna(0).astype("int64")
    )
    df["_score_num"] = pd.to_numeric(df.get("score"), errors="coerce").fillna(-1)
    df = df.sort_values(
        ["user_id", "_prioridad", "_score_num"],
        ascending=[True, False, False],
    )

    out = (
        df.groupby("user_id", as_index=False)
        .head(1)[CONTRATO_COLUMNS]
        .reset_index(drop=True)
    )
    return out

