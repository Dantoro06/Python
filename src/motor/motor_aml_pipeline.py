# -*- coding: utf-8 -*-
# motor_aml_pipeline.py
# ==========================================================
# AML Pipeline (2 capas): radar ratio + confirmacion hybrid
# ==========================================================

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# CAMBIO: imports con fallback para distintos contextos de ejecucion
try:
    from motor.aml_utils_io import cargar_base_apuestas, cargar_tabla_opcional
    from motor.motor_multi_cuenta import (
        _get_col,
        detectar_self_hedging,
        detectar_trios_multiusuario,
        normalizar_base,
        preparar_tabla_base_multicuenta,
    )
except Exception:
    from aml_utils_io import cargar_base_apuestas, cargar_tabla_opcional
    from motor_multi_cuenta import (
        _get_col,
        detectar_self_hedging,
        detectar_trios_multiusuario,
        normalizar_base,
        preparar_tabla_base_multicuenta,
    )


@dataclass
class _FechasApuesta:
    user_col: Optional[str]
    event_col: Optional[str]
    date_col: Optional[str]


def _safe_get_col(df: pd.DataFrame, aliases: list[str]) -> Optional[str]:
    try:
        return _get_col(df, aliases, obligatorio=False)
    except Exception:
        return None


def _norm_merge_key(series: pd.Series) -> pd.Series:
    """
    Normaliza claves de merge para evitar mismatch de dtype. # CAMBIO
    """
    s = series.astype(str).str.strip()
    s = s.replace({"nan": None, "None": None, "": None})
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().mean() > 0.95:
        return num.astype("Int64")
    return s.astype("string")
def _filtrar_merge_no_nulos(df: pd.DataFrame, key: str) -> pd.DataFrame:
    if key in df.columns:
        return df[df[key].notna()].copy()
    return df


def _detectar_columnas_apuesta(df_raw: pd.DataFrame) -> _FechasApuesta:
    # CAMBIO: deteccion suave de columnas temporales para features AML
    user_col = _safe_get_col(
        df_raw,
        [
            "Player Id",
            "playerid",
            "userid",
            "user_id",
            "player_id",
            "user",
            "usuario",
        ],
    )
    event_col = _safe_get_col(
        df_raw,
        ["Event name", "Evento", "Partido", "match", "event"],
    )
    date_col = _safe_get_col(
        df_raw,
        [
            "fecha_apuesta",
            "bet_time",
            "bet_date",
            "fecha",
            "date",
            "created_at",
        ],
    )
    return _FechasApuesta(user_col=user_col, event_col=event_col, date_col=date_col)


def _consolidar_candidatos(
    df_multi: pd.DataFrame,
    df_self: pd.DataFrame,
) -> pd.DataFrame:
    # CAMBIO: consolidacion estandar de candidatos ratio
    frames = []
    if df_multi is not None and not df_multi.empty:
        df_m = df_multi.copy()
        df_m["tipo_motor"] = "multi_cuenta"
        df_m["usuarios_involucrados"] = df_m["usuarios_implicados"]
        df_m["user_id_principal"] = (
            df_m["usuarios_implicados"].astype(str).str.split("\\|").str[0].str.strip()
        )
        df_m["event_id"] = df_m["event_name"]
        df_m["evidencia_resumen"] = (
            "Cobertura 1/X/2 multiusuario"
        )
        frames.append(df_m)

    if df_self is not None and not df_self.empty:
        df_s = df_self.copy()
        df_s["tipo_motor"] = "selfhedging"
        df_s["usuarios_involucrados"] = df_s["usuarios_implicados"]
        df_s["user_id_principal"] = df_s["usuarios_implicados"]
        df_s["event_id"] = df_s["event_name"]
        df_s["evidencia_resumen"] = "Self-hedging 1/X/2"
        frames.append(df_s)

    if not frames:
        columnas_base = [
            "case_id",
            "tipo_motor",
            "user_id_principal",
            "usuarios_involucrados",
            "event_id",
            "event_name",
            "total_apostado",
            "posible_ganancia_min",
            "posible_ganancia_max",
            "dif_rel_max_vs_total",
            "fecha_apuesta_min",
            "fecha_apuesta_max",
            "evidencia_resumen",
        ]
        return pd.DataFrame(columns=columnas_base)

    df = pd.concat(frames, ignore_index=True)
    df["case_id"] = (
        df["tipo_motor"].astype(str)
        + "|"
        + df["event_name"].astype(str)
        + "|"
        + df["usuarios_implicados"].astype(str)
    )
    df["event_name"] = df.get("event_name", df.get("event_id"))
    df["event_id"] = df.get("event_id", df.get("event_name"))
    df["posible_ganancia_min"] = df.get("posible_ganancia_min", np.nan)
    df["posible_ganancia_max"] = df.get("posible_ganancia_max", np.nan)
    df["dif_rel_max_vs_total"] = df.get("dif_rel_max_vs_total", np.nan)
    df["fecha_apuesta_min"] = pd.NaT
    df["fecha_apuesta_max"] = pd.NaT
    return df


def _agregar_fechas_apuesta(df_casos: pd.DataFrame, df_raw: pd.DataFrame) -> pd.DataFrame:
    # CAMBIO: fecha_apuesta_min/max si hay columnas disponibles y tipos unificados
    df_out = df_casos.copy()
    if df_out.empty:
        for col in ["fecha_apuesta_min", "fecha_apuesta_max"]:
            if col not in df_out.columns:
                df_out[col] = pd.NaT
            df_out[col] = pd.to_datetime(df_out[col], errors="coerce")
        return df_out

    cols = _detectar_columnas_apuesta(df_raw)
    user_col = None
    if "user_id" in df_raw.columns:
        user_col = "user_id"
    elif "Usuario" in df_raw.columns:
        user_col = "Usuario"
    elif "usuario" in df_raw.columns:
        user_col = "usuario"
    else:
        user_col = cols.user_col

    if not user_col or not cols.event_col or not cols.date_col:
        print("[WARNING] [AML] No se detectaron columnas de fecha para agregar fecha_apuesta_min/max.")
        if "fecha_apuesta_min" not in df_out.columns:
            df_out["fecha_apuesta_min"] = pd.NaT
        if "fecha_apuesta_max" not in df_out.columns:
            df_out["fecha_apuesta_max"] = pd.NaT
        df_out["fecha_apuesta_min"] = pd.to_datetime(df_out["fecha_apuesta_min"], errors="coerce")
        df_out["fecha_apuesta_max"] = pd.to_datetime(df_out["fecha_apuesta_max"], errors="coerce")
        return df_out

    df_raw_local = df_raw.copy()
    df_raw_local[user_col] = _norm_merge_key(df_raw_local[user_col])
    fechas = df_raw_local[[user_col, cols.event_col, cols.date_col]].copy()
    fechas = fechas.rename(
        columns={
            user_col: "user_id",
            cols.event_col: "event_name",
            cols.date_col: "fecha_apuesta",
        }
    )
    fechas["fecha_apuesta"] = pd.to_datetime(fechas["fecha_apuesta"], errors="coerce")
    fechas = fechas.dropna(subset=["fecha_apuesta"])
    if fechas.empty:
        if "fecha_apuesta_min" not in df_out.columns:
            df_out["fecha_apuesta_min"] = pd.NaT
        if "fecha_apuesta_max" not in df_out.columns:
            df_out["fecha_apuesta_max"] = pd.NaT
        df_out["fecha_apuesta_min"] = pd.to_datetime(df_out["fecha_apuesta_min"], errors="coerce")
        df_out["fecha_apuesta_max"] = pd.to_datetime(df_out["fecha_apuesta_max"], errors="coerce")
        return df_out

    fechas["user_id"] = _norm_merge_key(fechas["user_id"])
    fechas_agg = (
        fechas.groupby(["user_id", "event_name"])["fecha_apuesta"]
        .agg(["min", "max"])
        .reset_index()
        .rename(columns={"min": "fecha_apuesta_min", "max": "fecha_apuesta_max"})
    )

    df_out["_user_key"] = _norm_merge_key(df_out["user_id_principal"])

    mask_self = df_out["tipo_motor"] == "selfhedging"
    if mask_self.any():
        left = df_out.loc[mask_self, ["case_id", "_user_key", "event_name"]].copy()
        df_self = left.merge(
            fechas_agg,
            left_on=["_user_key", "event_name"],
            right_on=["user_id", "event_name"],
            how="left",
        )
        df_out.loc[mask_self, "fecha_apuesta_min"] = df_self["fecha_apuesta_min"].values
        df_out.loc[mask_self, "fecha_apuesta_max"] = df_self["fecha_apuesta_max"].values

    mask_multi = df_out["tipo_motor"] == "multi_cuenta"
    if mask_multi.any():
        df_multi = df_out[mask_multi][["case_id", "event_name", "usuarios_involucrados"]].copy()
        df_multi["user_id"] = df_multi["usuarios_involucrados"].astype(str).str.split("\\|")
        df_multi = df_multi.explode("user_id")
        df_multi["user_id"] = df_multi["user_id"].astype(str).str.strip()
        df_multi["user_id"] = _norm_merge_key(df_multi["user_id"])
        df_multi = df_multi.merge(
            fechas_agg,
            on=["user_id", "event_name"],
            how="left",
        )
        fechas_multi = (
            df_multi.groupby("case_id")[["fecha_apuesta_min", "fecha_apuesta_max"]]
            .agg({"fecha_apuesta_min": "min", "fecha_apuesta_max": "max"})
            .reset_index()
        )
        df_out = df_out.merge(fechas_multi, on="case_id", how="left", suffixes=("", "_multi"))
        df_out["fecha_apuesta_min"] = df_out["fecha_apuesta_min"].fillna(
            df_out["fecha_apuesta_min_multi"]
        )
        df_out["fecha_apuesta_max"] = df_out["fecha_apuesta_max"].fillna(
            df_out["fecha_apuesta_max_multi"]
        )
        df_out = df_out.drop(columns=["fecha_apuesta_min_multi", "fecha_apuesta_max_multi"])

    for col in ["fecha_apuesta_min", "fecha_apuesta_max"]:
        if col not in df_out.columns:
            df_out[col] = pd.NaT
        df_out[col] = pd.to_datetime(df_out[col], errors="coerce")

    df_out = df_out.drop(columns=["_user_key"], errors="ignore")
    return df_out

def _agregar_features_aml(
    df_casos: pd.DataFrame,
    df_raw: pd.DataFrame,
    df_depositos: Optional[pd.DataFrame],
    df_retiros: Optional[pd.DataFrame],
    df_kyc: Optional[pd.DataFrame],
) -> pd.DataFrame:
    # CAMBIO: features AML opcionales (depositos/retiros/kyc)
    df_out = df_casos.copy()
    if df_out.empty:
        for col in [
            "first_bet_time",
            "last_bet_time",
            "last_deposit_time",
            "first_withdraw_time",
            "fecha_apuesta_min",
            "fecha_apuesta_max",
        ]:
            if col not in df_out.columns:
                df_out[col] = pd.NaT
            df_out[col] = pd.to_datetime(df_out[col], errors="coerce")
        return df_out

    cols = _detectar_columnas_apuesta(df_raw)
    user_col = cols.user_col
    bet_date_col = cols.date_col
    if user_col and bet_date_col:
        apuestas = df_raw[[user_col, bet_date_col]].copy()
        apuestas = apuestas.rename(columns={user_col: "user_id", bet_date_col: "bet_date"})
        apuestas["user_id"] = _norm_merge_key(apuestas["user_id"])
        apuestas["bet_date"] = pd.to_datetime(apuestas["bet_date"], errors="coerce")
        apuestas = apuestas.dropna(subset=["bet_date"])
        bet_agg = (
            apuestas.groupby("user_id")["bet_date"]
            .agg(["min", "max"])
            .reset_index()
            .rename(columns={"min": "first_bet_time", "max": "last_bet_time"})
        )
    else:
        bet_agg = pd.DataFrame(columns=["user_id", "first_bet_time", "last_bet_time"])

    dep_agg = pd.DataFrame(columns=["user_id", "sum_deposit", "last_deposit_time"])
    if df_depositos is not None and not df_depositos.empty:
        dep_user = _safe_get_col(df_depositos, ["user_id", "userid", "player_id", "usuario"])
        dep_date = _safe_get_col(df_depositos, ["fecha_deposito", "deposit_date", "fecha", "date", "created_at"])
        dep_amount = _safe_get_col(df_depositos, ["monto_deposito", "deposito", "amount", "importe", "monto"])
        if dep_user and dep_date:
            cols = [dep_user, dep_date]
            if dep_amount and dep_amount in df_depositos.columns:
                cols.append(dep_amount)
            dep = df_depositos[cols].copy()
            dep = dep.rename(columns={dep_user: "user_id", dep_date: "deposit_date"})
            if dep_amount and dep_amount in dep.columns:
                dep = dep.rename(columns={dep_amount: "deposit_amount"})
                dep["deposit_amount"] = pd.to_numeric(dep["deposit_amount"], errors="coerce")
            else:
                dep["deposit_amount"] = np.nan
            dep["user_id"] = _norm_merge_key(dep["user_id"])
            dep["deposit_date"] = pd.to_datetime(dep["deposit_date"], errors="coerce")
            dep = dep.dropna(subset=["deposit_date"])
            dep_agg = (
                dep.groupby("user_id")
                .agg(
                    last_deposit_time=("deposit_date", "max"),
                    sum_deposit=("deposit_amount", "sum"),
                )
                .reset_index()
            )

    ret_agg = pd.DataFrame(columns=["user_id", "sum_withdraw", "first_withdraw_time"])
    if df_retiros is not None and not df_retiros.empty:
        ret_user = _safe_get_col(df_retiros, ["user_id", "userid", "player_id", "usuario"])
        ret_date = _safe_get_col(df_retiros, ["fecha_retiro", "withdraw_date", "fecha", "date", "created_at"])
        ret_amount = _safe_get_col(df_retiros, ["monto_retiro", "retiro", "withdraw", "amount", "importe", "monto"])
        if ret_user and ret_date:
            cols = [ret_user, ret_date]
            if ret_amount and ret_amount in df_retiros.columns:
                cols.append(ret_amount)
            ret = df_retiros[cols].copy()
            ret = ret.rename(columns={ret_user: "user_id", ret_date: "withdraw_date"})
            if ret_amount and ret_amount in ret.columns:
                ret = ret.rename(columns={ret_amount: "withdraw_amount"})
                ret["withdraw_amount"] = pd.to_numeric(ret["withdraw_amount"], errors="coerce")
            else:
                ret["withdraw_amount"] = np.nan
            ret["user_id"] = _norm_merge_key(ret["user_id"])
            ret["withdraw_date"] = pd.to_datetime(ret["withdraw_date"], errors="coerce")
            ret = ret.dropna(subset=["withdraw_date"])
            ret_agg = (
                ret.groupby("user_id")
                .agg(
                    first_withdraw_time=("withdraw_date", "min"),
                    sum_withdraw=("withdraw_amount", "sum"),
                )
                .reset_index()
            )

    kyc_agg = pd.DataFrame(columns=["user_id", "kyc_status", "account_age_days"])
    if df_kyc is not None and not df_kyc.empty:
        kyc_user = _safe_get_col(df_kyc, ["user_id", "userid", "player_id", "usuario"])
        kyc_status_col = _safe_get_col(df_kyc, ["kyc_status", "status", "verificado", "kyc"])
        kyc_created = _safe_get_col(df_kyc, ["fecha_creacion", "created_at", "fecha", "date"])
        if kyc_user:
            kyc = df_kyc[[kyc_user]].copy()
            kyc = kyc.rename(columns={kyc_user: "user_id"})
            if kyc_status_col and kyc_status_col in df_kyc.columns:
                kyc["kyc_status"] = df_kyc[kyc_status_col].astype(str)
            else:
                kyc["kyc_status"] = np.nan
            if kyc_created and kyc_created in df_kyc.columns:
                kyc_dates = pd.to_datetime(df_kyc[kyc_created], errors="coerce")
                kyc["account_age_days"] = (datetime.now() - kyc_dates).dt.days
            else:
                kyc["account_age_days"] = np.nan
            kyc["user_id"] = _norm_merge_key(kyc["user_id"])
            kyc_agg = kyc.drop_duplicates(subset=["user_id"])

    clean = df_out["user_id_principal"].astype(str).str.strip()
    clean = clean.replace({"nan": None, "None": None, "": None})
    clean.loc[clean.str.contains("\|", na=False)] = None
    clean.loc[clean.str.contains(",", na=False)] = None
    df_out["user_id_principal_clean"] = _norm_merge_key(clean)

    if "user_id" in bet_agg.columns:
        bet_agg["user_id"] = _norm_merge_key(bet_agg["user_id"])
    if "user_id" in dep_agg.columns:
        dep_agg["user_id"] = _norm_merge_key(dep_agg["user_id"])
    if "user_id" in ret_agg.columns:
        ret_agg["user_id"] = _norm_merge_key(ret_agg["user_id"])
    if "user_id" in kyc_agg.columns:
        kyc_agg["user_id"] = _norm_merge_key(kyc_agg["user_id"])

    df_out = df_out.merge(
        bet_agg,
        left_on="user_id_principal_clean",
        right_on="user_id",
        how="left",
    )
    df_out = df_out.merge(
        dep_agg,
        left_on="user_id_principal_clean",
        right_on="user_id",
        how="left",
        suffixes=("", "_dep"),
    )
    df_out = df_out.merge(
        ret_agg,
        left_on="user_id_principal_clean",
        right_on="user_id",
        how="left",
        suffixes=("", "_ret"),
    )
    df_out = df_out.merge(
        kyc_agg,
        left_on="user_id_principal_clean",
        right_on="user_id",
        how="left",
        suffixes=("", "_kyc"),
    )

    # CAMBIO: asegurar columnas de fecha y .dt seguro
    date_cols = [
        "first_bet_time",
        "last_bet_time",
        "last_deposit_time",
        "first_withdraw_time",
        "fecha_apuesta_min",
        "fecha_apuesta_max",
    ]
    for col in date_cols:
        if col not in df_out.columns:
            print(f"[WARNING] [AML] Falta columna de fecha: {col}. Se crea NaT.")
            df_out[col] = pd.NaT
        df_out[col] = pd.to_datetime(df_out[col], errors="coerce")

    delta = (df_out["fecha_apuesta_max"] - df_out["fecha_apuesta_min"])
    if not pd.api.types.is_timedelta64_dtype(delta):
        delta = pd.to_timedelta(delta, errors="coerce")
    df_out["duracion_apuestas_seg"] = delta.dt.total_seconds().fillna(0)

    df_out["deposit_to_bet_minutes"] = (
        (df_out["first_bet_time"] - df_out["last_deposit_time"])
        .dt.total_seconds()
        .div(60)
    )
    df_out["bet_to_withdraw_minutes"] = (
        (df_out["first_withdraw_time"] - df_out["last_bet_time"])
        .dt.total_seconds()
        .div(60)
    )
    df_out["withdraw_24h_flag"] = (
        df_out["bet_to_withdraw_minutes"].notna()
        & (df_out["bet_to_withdraw_minutes"] >= 0)
        & (df_out["bet_to_withdraw_minutes"] <= 24 * 60)
    )
    df_out["withdraw_vs_deposit_ratio"] = df_out["sum_withdraw"] / df_out["sum_deposit"]
    df_out.loc[df_out["sum_deposit"] <= 0, "withdraw_vs_deposit_ratio"] = np.nan

    return df_out

def _calcular_score_y_prioridad(df_casos: pd.DataFrame) -> pd.DataFrame:
    # CAMBIO: score AML sencillo y prioridad operativa
    df_out = df_casos.copy()
    df_out["entidad_id"] = np.where(
        df_out["tipo_motor"] == "selfhedging",
        df_out["user_id_principal"],
        df_out["usuarios_involucrados"],
    )
    df_out["entidad_tipo"] = np.where(
        df_out["tipo_motor"] == "selfhedging",
        "usuario",
        "red",
    )

    confirmados_por_entidad = (
        df_out.groupby("entidad_id")["confirmado_hybrid"].sum().reset_index()
    )
    confirmados_por_entidad = confirmados_por_entidad.rename(
        columns={"confirmado_hybrid": "n_confirmados_hybrid_entidad"}
    )
    df_out = df_out.merge(confirmados_por_entidad, on="entidad_id", how="left")

    p95 = df_out["total_apostado"].dropna().quantile(0.95) if not df_out.empty else 0.0

    score = pd.Series(0, index=df_out.index, dtype="int64")
    score += 30 * df_out["withdraw_24h_flag"].fillna(False).astype(int)
    score += 20 * (df_out["withdraw_vs_deposit_ratio"].fillna(0) >= 0.8).astype(int)
    score += 20 * (df_out["n_confirmados_hybrid_entidad"].fillna(0) >= 2).astype(int)
    score += 10 * (df_out["dif_rel_max_vs_total"].fillna(1) <= 0.02).astype(int)
    score += 10 * (df_out["total_apostado"].fillna(0) >= p95).astype(int)

    df_out["aml_score"] = score.clip(upper=100)
    df_out["prioridad"] = np.select(
        [df_out["aml_score"] >= 70, df_out["aml_score"] >= 40],
        ["ALTA", "MEDIA"],
        default="BAJA",
    )
    return df_out


def _generar_watchlist(df_casos: pd.DataFrame) -> pd.DataFrame:
    # CAMBIO: agregado por usuario/red para watchlist
    if df_casos.empty:
        return pd.DataFrame(
            columns=[
                "entidad_id",
                "entidad_tipo",
                "n_casos_ratio",
                "n_confirmados_hybrid",
                "total_exposicion",
                "top_eventos",
            ]
        )

    base = df_casos.copy()
    base["n_confirmados_hybrid"] = base["confirmado_hybrid"].astype(int)
    agg = (
        base.groupby(["entidad_id", "entidad_tipo"])
        .agg(
            n_casos_ratio=("case_id", "count"),
            n_confirmados_hybrid=("n_confirmados_hybrid", "sum"),
            total_exposicion=("total_apostado", "sum"),
        )
        .reset_index()
    )
    top_eventos = (
        base.groupby("entidad_id")["event_name"]
        .agg(lambda s: ", ".join(s.value_counts().head(3).index.astype(str)))
        .reset_index()
        .rename(columns={"event_name": "top_eventos"})
    )
    agg = agg.merge(top_eventos, on="entidad_id", how="left")
    return agg


def _sanity_check_aml(df_casos: pd.DataFrame) -> pd.DataFrame:

    """

    Validaciones basicas para evitar KeyError y .dt en AML. # CAMBIO

    """

    expected_cols = [

        "case_id",

        "tipo_motor",

        "user_id_principal",

        "usuarios_involucrados",

        "event_name",

        "total_apostado",

        "fecha_apuesta_min",

        "fecha_apuesta_max",

    ]

    missing = [c for c in expected_cols if c not in df_casos.columns]

    if missing:

        raise AssertionError(f"[AML] Faltan columnas esperadas: {missing}")

    date_cols = [

        "fecha_apuesta_min",

        "fecha_apuesta_max",

        "first_bet_time",

        "last_bet_time",

        "last_deposit_time",

        "first_withdraw_time",

    ]

    for col in date_cols:

        if col not in df_casos.columns:

            df_casos[col] = pd.NaT

        if not pd.api.types.is_datetime64_any_dtype(df_casos[col]):

            df_casos[col] = pd.to_datetime(df_casos[col], errors="coerce")

    return df_casos



def ejecutar_aml_pipeline(
    path_base_apuestas: str,
    modo_radar_ratio_min: float,
    modo_radar_ratio_max: float,
    tol_abs: float,
    k: float,
    tol_max: Optional[float],
    modo_confirmacion: str = "hybrid",
    ejecutar_selfhedging: bool = True,
    path_depositos: Optional[str] = None,
    path_retiros: Optional[str] = None,
    path_kyc: Optional[str] = None,
    out_dir: str = "reports",
) -> dict:
    # CAMBIO: orquestador AML 2 capas sin modificar motores existentes
    print("\n================= INICIANDO AML PIPELINE (2 CAPAS) =================\n")

    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    df_raw = cargar_base_apuestas(path_base_apuestas)
    if df_raw is None or df_raw.empty:
        raise ValueError("La base de apuestas esta vacia o no pudo cargarse.")

    # CAMBIO: normalizar y parsear fecha siempre
    df_raw = normalizar_base(df_raw)
    df_raw["fecha_apuesta"] = pd.to_datetime(df_raw["fecha_apuesta"], errors="coerce")

    df_base = preparar_tabla_base_multicuenta(df_raw)

    df_multi_ratio = detectar_trios_multiusuario(
        df_base,
        tolerancia_cobertura=0.10,
        min_total_apostado=0.0,
        max_apuestas_por_seleccion=20,
        ratio_min_margen=modo_radar_ratio_min,
        ratio_max_margen=modo_radar_ratio_max,
        tol_abs=tol_abs,
        k=k,
        tol_max=tol_max,
        modo_tolerancia="ratio",
        ruta_resultado=None,
    )

    if ejecutar_selfhedging:
        df_self_ratio = detectar_self_hedging(
            df_base,
            ratio_min_margen=modo_radar_ratio_min,
            ratio_max_margen=modo_radar_ratio_max,
            tol_abs=tol_abs,
            k=k,
            tol_max=tol_max,
            modo_tolerancia="ratio",
            ruta_resultados=None,
            guardar_detalle=False,
        )
    else:
        df_self_ratio = pd.DataFrame()

    df_casos = _consolidar_candidatos(df_multi_ratio, df_self_ratio)
    df_casos = _agregar_fechas_apuesta(df_casos, df_raw)
    df_casos["total_apostado"] = pd.to_numeric(df_casos["total_apostado"], errors="coerce")

    df_depositos = cargar_tabla_opcional(path_depositos)
    df_retiros = cargar_tabla_opcional(path_retiros)
    df_kyc = cargar_tabla_opcional(path_kyc)
    df_casos = _agregar_features_aml(
        df_casos,
        df_raw,
        df_depositos,
        df_retiros,
        df_kyc,
    )

    if "posible_ganancia_min" not in df_casos.columns:
        df_casos["posible_ganancia_min"] = np.nan
    if "posible_ganancia_max" not in df_casos.columns:
        df_casos["posible_ganancia_max"] = np.nan
    if "posible_ganancia_promedio" in df_casos.columns:
        df_casos["posible_ganancia_min"] = df_casos["posible_ganancia_min"].fillna(
            df_casos["posible_ganancia_promedio"]
        )
        df_casos["posible_ganancia_max"] = df_casos["posible_ganancia_max"].fillna(
            df_casos["posible_ganancia_promedio"]
        )

    if (modo_confirmacion or "hybrid").lower() != "hybrid":
        print(f"[AML] modo_confirmacion '{modo_confirmacion}' ignorado; se usa 'hybrid'.")

    tol_aplicada = np.maximum(tol_abs, k * df_casos["total_apostado"].astype(float))
    if tol_max is not None and not np.isnan(tol_max):
        tol_aplicada = np.minimum(tol_aplicada, tol_max)
    df_casos["tol_aplicada"] = tol_aplicada
    df_casos["tol_abs_usada"] = tol_abs
    df_casos["k_usado"] = k
    df_casos["tol_max_usada"] = tol_max

    dev_abs = np.maximum(
        (df_casos["posible_ganancia_min"] - df_casos["total_apostado"]).abs(),
        (df_casos["posible_ganancia_max"] - df_casos["total_apostado"]).abs(),
    )
    df_casos["dev_abs"] = dev_abs
    df_casos["confirmado_hybrid"] = df_casos["dev_abs"] <= df_casos["tol_aplicada"]

    df_casos = _calcular_score_y_prioridad(df_casos)
    df_casos = _sanity_check_aml(df_casos)

    radar_path = out_dir_path / "aml_radar_ratio.xlsx"
    cola_path = out_dir_path / "aml_cola_operativa_hybrid.xlsx"
    watchlist_path = out_dir_path / "aml_watchlist.xlsx"
    json_path = out_dir_path / "aml_pipeline.json"

    df_casos.to_excel(radar_path, index=False)
    df_casos[df_casos["confirmado_hybrid"]].to_excel(cola_path, index=False)
    df_watchlist = _generar_watchlist(df_casos)
    df_watchlist.to_excel(watchlist_path, index=False)

    resumen = {
        "candidatos_ratio_multi": int(0 if df_multi_ratio is None else len(df_multi_ratio)),
        "candidatos_ratio_self": int(0 if df_self_ratio is None else len(df_self_ratio)),
        "total_candidatos_ratio": int(len(df_casos)),
        "confirmados_hybrid": int(df_casos["confirmado_hybrid"].sum()) if not df_casos.empty else 0,
        "salidas": {
            "aml_radar_ratio": str(radar_path),
            "aml_cola_operativa_hybrid": str(cola_path),
            "aml_watchlist": str(watchlist_path),
            "aml_pipeline_json": str(json_path),
        },
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)

    print(f"[AML] candidatos_ratio_multi: {resumen['candidatos_ratio_multi']}")
    print(f"[AML] candidatos_ratio_self: {resumen['candidatos_ratio_self']}")
    print(f"[AML] total_candidatos_ratio: {resumen['total_candidatos_ratio']}")
    print(f"[AML] confirmados_hybrid: {resumen['confirmados_hybrid']}")
    if not df_casos.empty and "aml_score" in df_casos.columns:
        top = df_casos.sort_values("aml_score", ascending=False).head(5)
        print("[AML] Top 5 por score:")
        print(top[["case_id", "aml_score", "prioridad"]].to_string(index=False))

    print("\n================= AML PIPELINE FINALIZADO =================\n")
    return resumen
