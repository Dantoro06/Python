# -*- coding: utf-8 -*-
# motor_aml_pipeline_v0.py
# ==========================================================
# AML Pipeline REAL v0 (enchufable por registry)
# - Ejecuta motores desde un registro central
# - Mantiene contrato de salida y compatibilidad con GUI
# ==========================================================

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd

try:
    from motor.aml_utils_io import cargar_base_apuestas, cargar_tabla_opcional
    from motor.motor_multi_cuenta import preparar_tabla_base_multicuenta
    from motor.motores_registry import get_motores_registry
    from motor.pipeline_contracts import (
        CONTRATO_DETALLE_COLUMNS,
        consolidar_riesgo_global,
        normalizar_salida_motor,
    )
except Exception:
    from aml_utils_io import cargar_base_apuestas, cargar_tabla_opcional
    from motor_multi_cuenta import preparar_tabla_base_multicuenta
    from motores_registry import get_motores_registry
    from pipeline_contracts import (
        CONTRATO_DETALLE_COLUMNS,
        consolidar_riesgo_global,
        normalizar_salida_motor,
    )

try:
    from src.utils.paths_dashboard import REPORTS_DIR, DASHBOARD_DATA_DIR
except Exception:
    try:
        from utils.paths_dashboard import REPORTS_DIR, DASHBOARD_DATA_DIR
    except Exception:
        REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
        DASHBOARD_DATA_DIR = Path(__file__).resolve().parents[2] / "Data Dashboard"
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)


DEFAULT_CONFIG_BONUS_ABUSE: Dict = {
    "umbral_ratio_bono_deposito": 1.5,
    "umbral_horas_bono_retiro": 24,
    "umbral_cantidad_bonos": 3,
}
MAX_FILAS_JSON_DETALLE = 100000


def _resolver_motores_activos(
    ejecutar_multi_cuenta: bool,
    ejecutar_bonus_abuse: bool,
) -> List[str]:
    motores_activos: List[str] = []
    if bool(ejecutar_multi_cuenta):
        motores_activos.extend(["multi_cuenta", "self_hedging"])
    if bool(ejecutar_bonus_abuse):
        motores_activos.append("bonus_abuse")
    return motores_activos


def _armar_config_bonus_abuse(config_bonus_abuse: Optional[dict]) -> Dict:
    cfg = DEFAULT_CONFIG_BONUS_ABUSE.copy()
    if isinstance(config_bonus_abuse, dict):
        cfg.update(config_bonus_abuse)
    return cfg


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
    - path_bonos: (opcional) ruta base bonos si existe
    - out_dir: (opcional) carpeta de salida de reportes
    - return_summary:
        False -> retorna df_global
        True  -> retorna dict con totales y rutas
    """
    df_raw = cargar_base_apuestas(rutas_apuestas)
    if df_raw is None or df_raw.empty:
        raise ValueError("No se pudo cargar la base de apuestas o esta vacia.")

    # Base comun compartida para motores 1X2
    df_base = preparar_tabla_base_multicuenta(df_raw)
    # Bonos opcional, cargado una sola vez
    df_bonos = cargar_tabla_opcional(path_bonos) if path_bonos else pd.DataFrame()
    if df_bonos is None:
        df_bonos = pd.DataFrame()

    registry = get_motores_registry()
    motores_activos = _resolver_motores_activos(
        ejecutar_multi_cuenta=ejecutar_multi_cuenta,
        ejecutar_bonus_abuse=ejecutar_bonus_abuse,
    )

    shared_runtime = {}
    config_por_motor = {
        "multi_cuenta": {"_shared_runtime": shared_runtime},
        "self_hedging": {"_shared_runtime": shared_runtime},
        "bonus_abuse": _armar_config_bonus_abuse(config_bonus_abuse),
    }

    detecciones: List[pd.DataFrame] = []
    for motor_name in motores_activos:
        motor_spec = registry.get(motor_name)
        if motor_spec is None:
            print(f"[PIPELINE V0] WARNING: motor no registrado: {motor_name}")
            continue

        kwargs = {
            "config": config_por_motor.get(motor_name, {}),
        }
        if motor_spec.requiere_df_base:
            kwargs["df_base"] = df_base
        if motor_spec.requiere_df_raw:
            kwargs["df_raw"] = df_raw
        if motor_spec.requiere_bonos:
            kwargs["df_bonos"] = df_bonos

        df_motor = motor_spec.funcion_ejecucion(**kwargs)
        df_norm = normalizar_salida_motor(df_motor, motor_spec.nombre)
        if df_norm is not None and not df_norm.empty:
            detecciones.append(df_norm)

    detecciones_validas = [df for df in detecciones if df is not None and not df.empty]
    if detecciones_validas:
        df_detalle = pd.concat(detecciones_validas, ignore_index=True)
    else:
        df_detalle = pd.DataFrame(columns=CONTRATO_DETALLE_COLUMNS)

    df_global = consolidar_riesgo_global(df_detalle)

    reports_dir = Path(out_dir) if out_dir else REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    detalle_path = reports_dir / f"pipeline_detalle_{ts}.xlsx"
    global_path = reports_dir / f"pipeline_global_{ts}.xlsx"
    df_detalle.to_excel(detalle_path, index=False)
    df_global.to_excel(global_path, index=False)

    dashboard_global_json = DASHBOARD_DATA_DIR / "pipeline_global.json"
    df_global.to_json(dashboard_global_json, orient="records", force_ascii=False)

    dashboard_detalle_json = None
    dashboard_detalle_meta_json = None
    if len(df_detalle) <= MAX_FILAS_JSON_DETALLE:
        dashboard_detalle_json = DASHBOARD_DATA_DIR / "pipeline_detalle.json"
        df_detalle.to_json(dashboard_detalle_json, orient="records", force_ascii=False, date_format="iso")
    else:
        dashboard_detalle_meta_json = DASHBOARD_DATA_DIR / "pipeline_detalle_meta.json"
        meta = {
            "skipped": True,
            "rows": int(len(df_detalle)),
            "reason": f"Detalle omitido por tamano: supera {MAX_FILAS_JSON_DETALLE} filas.",
        }
        with dashboard_detalle_meta_json.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[PIPELINE V0] detalle: {detalle_path}")
    print(f"[PIPELINE V0] global:  {global_path}")
    print(f"[PIPELINE V0] global_json: {dashboard_global_json}")
    if dashboard_detalle_json is not None:
        print(f"[PIPELINE V0] detalle_json: {dashboard_detalle_json}")
    if dashboard_detalle_meta_json is not None:
        print(f"[PIPELINE V0] detalle_meta_json: {dashboard_detalle_meta_json}")

    if return_summary:
        return {
            "total_detecciones": int(len(df_detalle)),
            "total_usuarios": int(df_global["user_id"].nunique())
            if "user_id" in df_global.columns
            else 0,
            "salidas": {
                "detalle": str(detalle_path),
                "global": str(global_path),
                "pipeline_global_json": str(dashboard_global_json),
                **(
                    {"pipeline_detalle_json": str(dashboard_detalle_json)}
                    if dashboard_detalle_json is not None
                    else {}
                ),
                **(
                    {"pipeline_detalle_meta_json": str(dashboard_detalle_meta_json)}
                    if dashboard_detalle_meta_json is not None
                    else {}
                ),
            },
        }

    return df_global

