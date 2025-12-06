import sys
import os
import json
from pathlib import Path
from typing import Any, Dict, Optional

import altair as alt
import pandas as pd
import streamlit as st

# FIX de rutas (equivalente a app_hidding_bonus_tk.py)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.dashboard_riesgo import construir_reporte_riesgo_dict  # noqa: E402,F401

REPORTS_DIR = (
    Path(PROJECT_ROOT) / "reports"
    if (Path(PROJECT_ROOT) / "reports").exists()
    else Path(BASE_DIR) / "reports"
)
DATA_PATH = REPORTS_DIR / "reporte_riesgo_hiddingbonus.json"


def cargar_reporte(path: Path = DATA_PATH) -> Optional[Dict[str, Any]]:
    if not path.exists():
        st.warning(
            "No se encontró reporte_riesgo_hiddingbonus.json en reports/. Ejecuta el motor "
            "o coloca el archivo en la carpeta indicada."
        )
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        st.error("El archivo de reporte no contiene JSON válido.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer el reporte: {exc}")
    return None


def _df_niveles(estadisticas: Dict[str, Any], clave: str) -> pd.DataFrame:
    datos = estadisticas.get(clave, {}) or {}
    conteos = datos.get("por_nivel", {}) if isinstance(datos, dict) else {}
    return pd.DataFrame(
        [
            {"Nivel": nivel, "Casos": conteos.get(nivel, 0)}
            for nivel in ["ALTO", "MEDIO", "BAJO"]
        ]
    )


def render_abuse_view():
    st.title("🔥 Abuso de Bonus — Multiusuario y Self-Hedging")

    report = cargar_reporte()
    if not report:
        return

    estadisticas = report.get("estadisticas_riesgo", {})
    multi_df = _df_niveles(estadisticas, "multiusuario")
    self_df = _df_niveles(estadisticas, "self_hedging")

    col1, col2 = st.columns(2)
    col1.metric("Casos multiusuario", estadisticas.get("multiusuario", {}).get("casos_totales", 0))
    col2.metric("Casos self-hedging", estadisticas.get("self_hedging", {}).get("casos_totales", 0))

    st.caption(f"Fuente: {DATA_PATH}")

    st.subheader("Distribución de niveles de riesgo")
    col_a, col_b = st.columns(2)
    with col_a:
        st.write("Multiusuario")
        chart_multi = alt.Chart(multi_df).mark_bar(color="#1f77b4").encode(
            x="Nivel:N", y="Casos:Q", tooltip=["Nivel", "Casos"]
        )
        st.altair_chart(chart_multi, use_container_width=True)
        st.dataframe(multi_df, use_container_width=True)

    with col_b:
        st.write("Self-Hedging")
        chart_self = alt.Chart(self_df).mark_bar(color="#ff7f0e").encode(
            x="Nivel:N", y="Casos:Q", tooltip=["Nivel", "Casos"]
        )
        st.altair_chart(chart_self, use_container_width=True)
        st.dataframe(self_df, use_container_width=True)


render_abuse_view()
