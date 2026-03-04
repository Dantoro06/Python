# -*- coding: utf-8 -*-
# motor_aml_pipeline_v0.py
# ==========================================================
# AML Pipeline REAL v0 (minimo, funcional y extensible)
# - Integra: Multi-Cuenta (multiusuario + self-hedging)
# - Integra: Bonus Abuse (por usuario)
# ==========================================================

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Union

import pandas as pd


# -----------------------------
# Imports con fallback
# -----------------------------
try:
    from motor.aml_utils_io import cargar_base_apuestas, cargar_tabla_opcional
    from motor.motor_multi_cuenta import (
        preparar_tabla_base_multicuenta,
        ejecutar_motor_multicuenta,
    )
except Exception:
    from aml_utils_io import cargar_base_apuestas, cargar_tabla_opcional
    from motor_multi_cuenta import (
        preparar_tabla_base_multicuenta,
        ejecutar_motor_multicuenta,
    )

try:
    # En este proyecto, bonus abuse suele estar a nivel src/
    from motor_bonus_abuse import ejecutar as ejecutar_bonus_abuse_fn
except Exception:
    try:
        from motor.motor_bonus_abuse import ejecutar as ejecutar_bonus_abuse_fn
    except Exception:
        # último fallback (si se ejecuta como paquete)
        from .motor_bonus_abuse import ejecutar as ejecutar_bonus_abuse_fn

# -----------------------------
# Contrato estándar
# -----------------------------
CONTRATO_COLUMNS = [
    "user_id",
    "motor",
    "nivel_riesgo",
    "score",
    "flags",
    "evidencia",
]


# Defaults Bonus Abuse (mismo criterio del GUI)
DEFAULT_CONFIG_BONUS_ABUSE: Dict = {
    "umbral_ratio_bono_deposito": 1.5,
    "umbral_horas_bono_retiro": 24,
    "umbral_cantidad_bonos": 3,
}


# -----------------------------
# Helpers
# -----------------------------
def _is_na(v) -> bool:
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except Exception:
        return False


def _coerce_user_id(v) -> Optional[str]:
    """
    Normaliza user_id a string estable (evita '101.0').
    """
    if _is_na(v):
        return None
    s = str(v).strip()
    if not s:
        return None
    # Quitar sufijo '.0' típico de floats
    if s.endswith(".0"):
        s2 = s[:-2]
        if s2.isdigit():
            return s2
    return s


def _coerce_text(v) -> Optional[str]:
    if _is_na(v):
        return None
    return str(v)


def normalizar_salida_motor(df: pd.DataFrame, motor_name: str) -> pd.DataFrame:
    """
    Normaliza la salida de un motor al contrato estandar.
    - Asegura columnas del contrato
    - 'motor' se fija con motor_name
    - user_id se normaliza a string estable
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=CONTRATO_COLUMNS)

    df_out = df.copy()
    df_out["motor"] = motor_name

    if "user_id" not in df_out.columns:
        df_out["user_id"] = None
    df_out["user_id"] = df_out["user_id"].map(_coerce_user_id)

    if "nivel_riesgo" not in df_out.columns:
        df_out["nivel_riesgo"] = None
    df_out["nivel_riesgo"] = df_out["nivel_riesgo"].map(lambda x: None if _is_na(x) else str(x).upper().strip())

    if "score" not in df_out.columns:
        df_out["score"] = None
    if "flags" not in df_out.columns:
        df_out["flags"] = None
    if "evidencia" not in df_out.columns:
        df_out["evidencia"] = None

    df_out["flags"] = df_out["flags"].map(_coerce_text)
    df_out["evidencia"] = df_out["evidencia"].map(_coerce_text)

    return df_out[CONTRATO_COLUMNS]


def _prioridad_riesgo() -> Dict[str, int]:
    # Nota: CRITICO existe en Bonus Abuse.
    return {"BAJO": 1, "MEDIO": 2, "ALTO": 3, "CRITICO": 4}


def _consolidar_riesgo_global(df_detalle: pd.DataFrame) -> pd.DataFrame:
    """
    Devuelve 1 fila por user_id con la detección de mayor prioridad,
    manteniendo columnas del contrato para trazabilidad (motor/flags/evidencia).
    """
    if df_detalle is None or df_detalle.empty:
        return pd.DataFrame(columns=CONTRATO_COLUMNS)

    df = df_detalle.copy()
    df = df[df["user_id"].notna()].copy()
    if df.empty:
        return pd.DataFrame(columns=CONTRATO_COLUMNS)

    prioridad = _prioridad_riesgo()
    df["_prioridad"] = df["nivel_riesgo"].map(prioridad).fillna(0).astype(int)

    # En empates: prioriza el que tenga score más alto si existe, si no el primero
    if "score" in df.columns:
        df["_score_num"] = pd.to_numeric(df["score"], errors="coerce").fillna(-1)
    else:
        df["_score_num"] = -1

    df = df.sort_values(["user_id", "_prioridad", "_score_num"], ascending=[True, False, False])
    df_max = df.groupby("user_id", as_index=False).head(1)[CONTRATO_COLUMNS].reset_index(drop=True)

    return df_max


def _resumir_bonus_abuse_por_usuario(df_bonus: pd.DataFrame) -> pd.DataFrame:
    """
    Reduce la salida de Bonus Abuse a 1 fila por user_id para evitar explosión.
    Genera:
      - score (max)
      - nivel_riesgo (por prioridad)
      - flags (consolidado)
      - evidencia (resumen corto)
    """
    if df_bonus is None or df_bonus.empty:
        return pd.DataFrame(columns=["user_id", "nivel_riesgo", "score", "flags", "evidencia"])

    df = df_bonus.copy()

    # Normalizar columnas esperadas del motor
    if "nivel_riesgo_bonus" in df.columns and "nivel_riesgo" not in df.columns:
        df["nivel_riesgo"] = df["nivel_riesgo_bonus"]
    if "score_bonus_abuse" in df.columns and "score" not in df.columns:
        df["score"] = df["score_bonus_abuse"]

    for col in ["ratio_bono_deposito", "horas_bono_retiro", "cantidad_bonos"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Flags conocidos del motor
    flag_cols = [c for c in ["flag_ratio_alto", "flag_retiro_rapido", "flag_frecuencia_alta"] if c in df.columns]
    for c in flag_cols:
        df[c] = df[c].fillna(False).astype(bool)

    # Normalizar user_id
    if "user_id" not in df.columns:
        df["user_id"] = None
    df["user_id"] = df["user_id"].map(_coerce_user_id)
    df = df[df["user_id"].notna()].copy()
    if df.empty:
        return pd.DataFrame(columns=["user_id", "nivel_riesgo", "score", "flags", "evidencia"])

    # Prioridad por nivel
    prioridad = _prioridad_riesgo()
    df["nivel_riesgo"] = df["nivel_riesgo"].map(lambda x: None if _is_na(x) else str(x).upper().strip())
    df["_prio"] = df["nivel_riesgo"].map(prioridad).fillna(0).astype(int)
    df["_score_num"] = pd.to_numeric(df["score"], errors="coerce").fillna(-1)

    def agg_flags(grp: pd.DataFrame) -> str:
        if not flag_cols:
            return "bonus_abuse"
        activos = []
        for c in flag_cols:
            if grp[c].any():
                activos.append(c.replace("flag_", ""))
        return "|".join(activos) if activos else "bonus_abuse"

    def agg_evidencia(grp: pd.DataFrame) -> str:
        ratio_max = float(grp["ratio_bono_deposito"].max()) if "ratio_bono_deposito" in grp.columns else float("nan")
        horas_min = float(grp["horas_bono_retiro"].min()) if "horas_bono_retiro" in grp.columns else float("nan")
        cant = float(grp["cantidad_bonos"].max()) if "cantidad_bonos" in grp.columns else float("nan")

        partes = []
        if ratio_max == ratio_max:
            partes.append(f"ratio_max={round(ratio_max, 3)}")
        if horas_min == horas_min:
            partes.append(f"horas_min={round(horas_min, 2)}")
        if cant == cant:
            partes.append(f"bonos={int(cant)}" if cant.is_integer() else f"bonos={round(cant, 2)}")
        return " | ".join(partes) if partes else "resumen_bonus_abuse"

    # Agregado por usuario
    agg = (
        df.groupby("user_id", as_index=False)
        .apply(lambda g: pd.Series({
            "score": float(g["_score_num"].max()),
            "nivel_riesgo": g.sort_values(["_prio", "_score_num"], ascending=[False, False]).iloc[0]["nivel_riesgo"],
            "flags": agg_flags(g),
            "evidencia": agg_evidencia(g),
        }))
        .reset_index(drop=True)
    )

    return agg[["user_id", "nivel_riesgo", "score", "flags", "evidencia"]]


# -----------------------------
# Pipeline principal
# -----------------------------
def ejecutar_pipeline_aml_v0(
    rutas_apuestas,
    ejecutar_multi_cuenta: bool = True,
    ejecutar_bonus_abuse: bool = True,
    path_bonos: Optional[str] = None,
    out_dir: Optional[str] = None,
    return_summary: bool = False,
    config_bonus_abuse: Optional[dict] = None,
) -> Union[pd.DataFrame, dict]:
    """
    Ejecuta el pipeline AML v0.

    - rutas_apuestas: ruta o lista de rutas (CSV/Excel) para apuestas
    - path_bonos: (opcional) ruta base bonos si existe, si no se intenta inferir desde apuestas
    - out_dir: (opcional) carpeta de salida de reportes
    - return_summary:
        False -> retorna df_global (compatibilidad)
        True  -> retorna resumen dict con totales y rutas
    """
    df_raw = cargar_base_apuestas(rutas_apuestas)
    if df_raw is None or df_raw.empty:
        raise ValueError("No se pudo cargar la base de apuestas o esta vacía.")

    # Base común (no se debe modificar in-place)
    df_base = preparar_tabla_base_multicuenta(df_raw)

    detecciones = []

    # ---------------- Bonus Abuse ----------------
    run_bonus_abuse = bool(ejecutar_bonus_abuse)
    if run_bonus_abuse:
        cfg = (config_bonus_abuse or {}).copy()
        for k, v in DEFAULT_CONFIG_BONUS_ABUSE.items():
            cfg.setdefault(k, v)

        df_bonos = cargar_tabla_opcional(path_bonos) if path_bonos else pd.DataFrame()

        df_bonus_detalle, _metricas = ejecutar_bonus_abuse_fn(
            df_raw,  # usa df_raw para poder aprovechar columnas de bonos si están incluidas
            pd.DataFrame(),
            df_bonos if df_bonos is not None else pd.DataFrame(),
            pd.DataFrame(),
            cfg,
        )

        df_bonus_user = _resumir_bonus_abuse_por_usuario(df_bonus_detalle)
        df_bonus_user = normalizar_salida_motor(df_bonus_user, "bonus_abuse")
        if not df_bonus_user.empty:
            detecciones.append(df_bonus_user)

    # ---------------- Multi-cuenta + Self-hedging ----------------
    if ejecutar_multi_cuenta:
        df_multi, df_self = ejecutar_motor_multicuenta(df_base.copy())

        if df_multi is not None and not df_multi.empty:
            df_m = df_multi.copy()
            if "usuarios_implicados" in df_m.columns:
                df_m["user_id"] = df_m["usuarios_implicados"].astype(str).str.split("|")
                df_m = df_m.explode("user_id")
                df_m["user_id"] = df_m["user_id"].astype(str).str.strip()
            df_m["flags"] = "multi_cuenta"
            if "selecciones_por_usuario" in df_m.columns:
                df_m["evidencia"] = df_m["selecciones_por_usuario"].map(_coerce_text)
            # asegurar columna nivel_riesgo (algunos outputs la llaman nivel_riesgo)
            if "nivel_riesgo" not in df_m.columns and "nivel_riesgo_multi" in df_m.columns:
                df_m["nivel_riesgo"] = df_m["nivel_riesgo_multi"]
            df_m = normalizar_salida_motor(df_m, "multi_cuenta")
            detecciones.append(df_m)

        if df_self is not None and not df_self.empty:
            df_s = df_self.copy()
            if "usuarios_implicados" in df_s.columns:
                df_s["user_id"] = df_s["usuarios_implicados"]
            df_s["flags"] = "self_hedging"
            if "selecciones_por_usuario" in df_s.columns:
                df_s["evidencia"] = df_s["selecciones_por_usuario"].map(_coerce_text)
            if "nivel_riesgo" not in df_s.columns and "nivel_riesgo_self" in df_s.columns:
                df_s["nivel_riesgo"] = df_s["nivel_riesgo_self"]
            df_s = normalizar_salida_motor(df_s, "self_hedging")
            detecciones.append(df_s)

    df_detalle = (
        pd.concat(detecciones, ignore_index=True)
        if detecciones
        else pd.DataFrame(columns=CONTRATO_COLUMNS)
    )

    df_global = _consolidar_riesgo_global(df_detalle)

    # Export
    reports_dir = Path(out_dir) if out_dir else (Path(__file__).resolve().parents[2] / "reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    detalle_path = reports_dir / f"pipeline_detalle_{ts}.xlsx"
    global_path = reports_dir / f"pipeline_global_{ts}.xlsx"

    df_detalle.to_excel(detalle_path, index=False)
    df_global.to_excel(global_path, index=False)

    print(f"[PIPELINE V0] detalle: {detalle_path}")
    print(f"[PIPELINE V0] global:  {global_path}")

    if return_summary:
        return {
            "total_detecciones": int(len(df_detalle)),
            "total_usuarios": int(df_global["user_id"].nunique()) if "user_id" in df_global.columns else 0,
            "salidas": {
                "detalle": str(detalle_path),
                "global": str(global_path),
            },
        }

    return df_global


# Smoke test (ejemplo minimo)
# df_global = ejecutar_pipeline_aml_v0("ruta/a/apuestas.csv")
# assert "user_id" in df_global.columns
