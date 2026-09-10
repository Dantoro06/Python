import sys
import os
import json
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st

# === HABILITAR IMPORTS DESDE src/ ===
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# FIX de rutas (equivalente a app_hidding_bonus_tk.py)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


try:
    from src.utils.paths_dashboard import DASHBOARD_DATA_DIR, REPORTS_DIR
except Exception:
    from utils.paths_dashboard import DASHBOARD_DATA_DIR, REPORTS_DIR


def cargar_json(nombre: str) -> Path:
    p1 = DASHBOARD_DATA_DIR / nombre
    p2 = REPORTS_DIR / nombre
    if p1.exists():
        return p1
    if p2.exists():
        return p2
    raise FileNotFoundError(
        f"No se encontro '{nombre}' en '{DASHBOARD_DATA_DIR}' ni en '{REPORTS_DIR}'."
    )


DATA_PATH = DASHBOARD_DATA_DIR / "reporte_riesgo_multicuenta.json"


def cargar_reporte(path: Path = DATA_PATH) -> Optional[Dict[str, Any]]:
    try:
        path = cargar_json("reporte_riesgo_multicuenta.json")
    except FileNotFoundError:
        st.warning(
            "No hay reporte actual. Coloca reporte_riesgo_multicuenta.json en Data Dashboard/ "
            "o ejecuta el motor para generarlo."
        )
        return None

    try:
        with path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            st.error("El reporte debe ser un JSON con objeto raíz (dict).")
            return None
        return data
    except json.JSONDecodeError:
        st.error("El reporte actual no tiene un formato JSON válido.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer el reporte: {exc}")
    return None


def render_last_run():
    st.set_page_config(page_title="Risk Monitor PRO — Última Ejecución")
    st.title("Risk Monitor PRO — Última Ejecución")

    report = cargar_reporte()
    if not report:
        return

    resumen = report.get("resumen_ejecucion", {})
    meta = report.get("metadata", {})
    estadisticas = report.get("estadisticas_riesgo", {})

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total transacciones", resumen.get("total_transacciones", 0))
    col2.metric("Usuarios analizados", resumen.get("usuarios_analizados", 0))
    col3.metric("Eventos analizados", resumen.get("eventos_analizados", 0))
    ratio = float(resumen.get("ratio_sospecha_global", 0.0)) * 100
    col4.metric("Ratio sospecha global", f"{ratio:.2f}%")

    st.markdown(
        f"**Fecha de ejecución:** {meta.get('fecha_ejecucion', '—')} · "
        f"Duración (seg): {resumen.get('tiempo_proceso_seg', '—')} · "
        f"Archivos analizados: {len(meta.get('archivos_procesados', []) or [])}"
    )

    st.subheader("Riesgo por fuente")
    multi = estadisticas.get("multiusuario", {})
    self_h = estadisticas.get("self_hedging", {})

    col_a, col_b = st.columns(2)
    col_a.metric("Casos multiusuario", multi.get("casos_totales", 0))
    col_b.metric("Casos self-hedging", self_h.get("casos_totales", 0))

    st.subheader("Top usuarios de riesgo")
    st.caption("Información leída directamente del JSON generado por el motor.")
    st.json(
        report.get("top_usuarios_riesgo", []),
        expanded=False,
    )


render_last_run()
