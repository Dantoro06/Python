import sys
import os
import json
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
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


def _valor_visual(valor):
    return "—" if pd.isna(valor) else valor


def _etiqueta_motor(motor):
    return {
        "multi_cuenta": "Multi-Cuenta",
        "multiusuario": "Multi-Cuenta",
        "self_hedging": "Self-Hedging",
        "bonus_abuse": "Abuso de Bonos",
    }.get(motor, motor)


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
    col1.metric("Transacciones analizadas 1X2", _valor_visual(resumen.get("total_transacciones", 0)))
    col2.metric("Usuarios analizados 1X2", _valor_visual(resumen.get("usuarios_analizados", 0)))
    col3.metric("Eventos analizados 1X2", _valor_visual(resumen.get("eventos_analizados", 0)))
    ratio = resumen.get("ratio_sospecha_global", 0.0)
    ratio_visual = "—" if pd.isna(ratio) else f"{float(ratio) * 100:.2f}%"
    col4.metric("Ratio de sospecha 1X2", ratio_visual)

    st.markdown(
        f"**Fecha de ejecución:** {_valor_visual(meta.get('fecha_ejecucion', '—'))} · "
        f"Duración (seg): {_valor_visual(resumen.get('tiempo_proceso_seg', '—'))} · "
        f"Archivos procesados: {len(meta.get('archivos_procesados', []) or [])}"
    )

    st.subheader("Detecciones por tipo de riesgo")
    multi = estadisticas.get("multiusuario", {})
    self_h = estadisticas.get("self_hedging", {})

    col_a, col_b = st.columns(2)
    col_a.metric("Casos Multi-Cuenta", _valor_visual(multi.get("casos_totales", 0)))
    col_b.metric("Casos Self-Hedging", _valor_visual(self_h.get("casos_totales", 0)))

    st.subheader("Top usuarios de riesgo")
    st.caption("Usuarios con detecciones de riesgo en la última ejecución.")
    usuarios_visual = pd.DataFrame(report.get("top_usuarios_riesgo", [])).copy()
    if "tipos_riesgo" in usuarios_visual.columns:
        usuarios_visual["tipos_riesgo"] = usuarios_visual["tipos_riesgo"].map(
            lambda tipos: [_etiqueta_motor(motor) for motor in tipos]
            if isinstance(tipos, list) else _etiqueta_motor(tipos)
        )
    usuarios_visual = usuarios_visual.rename(columns={
        "usuario_id": "Usuario", "casos_total": "Detecciones",
        "casos_multiusuario": "Multi-Cuenta", "casos_self_hedging": "Self-Hedging",
        "eventos_involucrados": "Eventos", "tipos_riesgo": "Riesgo detectado",
    })
    usuarios_visual = usuarios_visual.astype(object).where(usuarios_visual.notna(), "—")
    st.dataframe(usuarios_visual, use_container_width=True)


render_last_run()
