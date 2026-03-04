# motor_bonus_abuse.py
# =====================================================
# Motor de Riesgo - Bonus Abuse (FIX DEFENSIVO FINAL)
# Proyecto: Motor de Riesgo Nueve11
#
# - Tolerante a data incompleta
# - No asume columnas
# - No asume fechas válidas
# - No debe romper nunca la ejecución
# =====================================================

from typing import Tuple, Dict
import pandas as pd
import numpy as np


def _asegurar_columna(df: pd.DataFrame, col: str):
    if col not in df.columns:
        df[col] = np.nan


def _calcular_ratio_bono_deposito(df_bonos: pd.DataFrame) -> pd.DataFrame:
    df = df_bonos.copy()
    _asegurar_columna(df, "deposito")
    _asegurar_columna(df, "monto_bono")

    df["ratio_bono_deposito"] = np.where(
        df["deposito"] > 0,
        df["monto_bono"] / df["deposito"],
        np.nan
    )
    return df


def _calcular_tiempo_bono_retiro(df_bonos: pd.DataFrame) -> pd.DataFrame:
    df = df_bonos.copy()
    _asegurar_columna(df, "fecha_bono")
    _asegurar_columna(df, "fecha_retiro")

    fecha_bono = pd.to_datetime(df["fecha_bono"], errors="coerce")
    fecha_retiro = pd.to_datetime(df["fecha_retiro"], errors="coerce")

    df["horas_bono_retiro"] = np.nan
    mask_validas = fecha_bono.notna() & fecha_retiro.notna()

    if mask_validas.any():
        df.loc[mask_validas, "horas_bono_retiro"] = (
            (fecha_retiro[mask_validas] - fecha_bono[mask_validas])
            .dt.total_seconds() / 3600
        )
    return df


def _calcular_frecuencia_bonos(df_bonos: pd.DataFrame) -> pd.DataFrame:
    _asegurar_columna(df_bonos, "user_id")
    return (
        df_bonos
        .groupby("user_id", dropna=False)
        .size()
        .reset_index(name="cantidad_bonos")
    )


def ejecutar(
    df_apuestas: pd.DataFrame,
    df_usuarios: pd.DataFrame,
    df_bonos: pd.DataFrame,
    df_wallets: pd.DataFrame,
    config: Dict
) -> Tuple[pd.DataFrame, Dict]:

    # Carga defensiva de la base de bonos desde la base estándar si viene vacía
    if df_bonos is not None and not df_bonos.empty:
        bonos = df_bonos.copy()
    else:
        if "bono_id" in df_apuestas.columns:
            bonos = df_apuestas[df_apuestas["bono_id"].notna()].copy()
        else:
            bonos = pd.DataFrame()

    for col in [
        "user_id",
        "monto_bono",
        "deposito",
        "fecha_bono",
        "fecha_retiro",
        "estado_bono",
    ]:
        _asegurar_columna(bonos, col)

    bonos = _calcular_ratio_bono_deposito(bonos)
    bonos = _calcular_tiempo_bono_retiro(bonos)

    freq = _calcular_frecuencia_bonos(bonos)
    bonos = bonos.merge(freq, on="user_id", how="left")

    bonos["flag_ratio_alto"] = (
        bonos["ratio_bono_deposito"] >= config.get("umbral_ratio_bono_deposito", 1.5)
    )

    bonos["flag_retiro_rapido"] = (
        bonos["horas_bono_retiro"].notna()
        & (bonos["horas_bono_retiro"] <= config.get("umbral_horas_bono_retiro", 24))
        & bonos["estado_bono"].isin(["LIBERADO", "RETIRADO"])
    )

    bonos["flag_frecuencia_alta"] = (
        bonos["cantidad_bonos"] >= config.get("umbral_cantidad_bonos", 3)
    )

    bonos["score_bonus_abuse"] = (
        bonos["flag_ratio_alto"].astype(int) * 40 +
        bonos["flag_retiro_rapido"].astype(int) * 35 +
        bonos["flag_frecuencia_alta"].astype(int) * 25
    ).clip(0, 100)

    def clasificar(score):
        if score >= 80:
            return "CRITICO"
        if score >= 60:
            return "ALTO"
        if score >= 30:
            return "MEDIO"
        return "BAJO"

    bonos["nivel_riesgo_bonus"] = bonos["score_bonus_abuse"].apply(clasificar)

    mask_sin_impacto = bonos["estado_bono"].isin(["CANCELADO", "EXPIRADO"])
    bonos.loc[mask_sin_impacto, "nivel_riesgo_bonus"] = "BAJO"

    resultado_df = bonos[
        [
            "user_id",
            "estado_bono",
            "monto_bono",
            "deposito",
            "ratio_bono_deposito",
            "horas_bono_retiro",
            "cantidad_bonos",
            "score_bonus_abuse",
            "nivel_riesgo_bonus",
            "flag_ratio_alto",
            "flag_retiro_rapido",
            "flag_frecuencia_alta",
        ]
    ].copy()

    metricas = {
        "usuarios_analizados": resultado_df["user_id"].nunique(dropna=True),
        "usuarios_riesgo_alto_critico": resultado_df[
            resultado_df["nivel_riesgo_bonus"].isin(["ALTO", "CRITICO"])
        ]["user_id"].nunique(dropna=True),
        "score_promedio": float(resultado_df["score_bonus_abuse"].mean())
    }

    return resultado_df, metricas
