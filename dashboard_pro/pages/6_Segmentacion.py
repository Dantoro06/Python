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
REPORTE_PATH = REPORTS_DIR / "reporte_riesgo_hiddingbonus.json"
HISTORICO_PATH = REPORTS_DIR / "historico_riesgo_hiddingbonus.json"


def cargar_reporte(path: Path = REPORTE_PATH) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def cargar_historico(path: Path = HISTORICO_PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()

    ejecuciones = data.get("ejecuciones", [])
    if not ejecuciones:
        return pd.DataFrame()

    df_hist = pd.DataFrame(ejecuciones)
    if "fecha_ejecucion" in df_hist.columns:
        df_hist["fecha_ejecucion"] = pd.to_datetime(
            df_hist["fecha_ejecucion"], errors="coerce"
        )
    return df_hist


def render_segmentation_view():
    st.title("📊 Segmentación de Riesgo — PRO")

    report = cargar_reporte()
    historico_df = cargar_historico()

    if historico_df.empty:
        st.warning(
            "No hay histórico disponible para segmentar. Ejecuta el motor para generar "
            "reports/historico_riesgo_hiddingbonus.json."
        )
    else:
        st.subheader("Evolución de casos por tipo")
        if {"casos_multiusuario", "casos_self_hedging"}.issubset(historico_df.columns):
            melted = historico_df.melt(
                id_vars=["fecha_ejecucion"],
                value_vars=["casos_multiusuario", "casos_self_hedging"],
                var_name="tipo",
                value_name="casos",
            )
            chart = (
                alt.Chart(melted)
                .mark_area(opacity=0.5)
                .encode(
                    x="fecha_ejecucion:T",
                    y="casos:Q",
                    color=alt.Color(
                        "tipo:N",
                        scale=alt.Scale(
                            domain=["casos_multiusuario", "casos_self_hedging"],
                            range=["#1f77b4", "#ff7f0e"],
                        ),
                        title="Tipo",
                    ),
                    tooltip=["fecha_ejecucion:T", "tipo:N", "casos:Q"],
                )
            )
            st.altair_chart(chart, use_container_width=True)

        if "ratio_sospecha_global" in historico_df.columns:
            st.subheader("Ratio de sospecha global")
            graf_ratio = (
                alt.Chart(historico_df)
                .mark_line(point=True)
                .encode(
                    x="fecha_ejecucion:T",
                    y="ratio_sospecha_global:Q",
                    tooltip=["fecha_ejecucion:T", "ratio_sospecha_global:Q"],
                )
            )
            st.altair_chart(graf_ratio, use_container_width=True)

    st.subheader("Parámetros de la última ejecución")
    if not report:
        st.info("Aún no hay reporte actual para mostrar parámetros.")
        return

    params = report.get("parametros_motor", {})
    st.json(params, expanded=False)


render_segmentation_view()
