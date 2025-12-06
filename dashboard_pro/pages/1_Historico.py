import sys
import os
import json
from pathlib import Path

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
DATA_PATH = REPORTS_DIR / "historico_riesgo_hiddingbonus.json"


def cargar_historico(path: Path = DATA_PATH) -> pd.DataFrame:
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


def render_history():
    st.title("📈 Histórico de Riesgo")

    df = cargar_historico()
    if df.empty:
        st.warning(
            "No hay histórico disponible. Asegúrate de que reports/historico_riesgo_hiddingbonus.json "
            "exista y vuelva a cargar la aplicación."
        )
        return

    st.caption(f"Fuente: {DATA_PATH}")

    if "ratio_sospecha_global" in df.columns:
        graf_ratio = (
            alt.Chart(df)
            .mark_line(point=True)
            .encode(
                x=alt.X("fecha_ejecucion:T", title="Fecha"),
                y=alt.Y("ratio_sospecha_global:Q", title="Ratio de sospecha"),
                tooltip=["fecha_ejecucion:T", "ratio_sospecha_global:Q"],
            )
        )
        st.subheader("Evolución del ratio de sospecha")
        st.altair_chart(graf_ratio, use_container_width=True)

    if {"transacciones_totales", "total_casos_detectados"}.issubset(df.columns):
        st.subheader("Resumen de ejecuciones")
        graf_totales = (
            alt.Chart(df)
            .transform_fold(
                ["transacciones_totales", "total_casos_detectados"],
                as_=["Indicador", "Valor"],
            )
            .mark_bar()
            .encode(
                x="fecha_ejecucion:T",
                y="Valor:Q",
                color="Indicador:N",
                tooltip=["fecha_ejecucion:T", "Indicador:N", "Valor:Q"],
            )
        )
        st.altair_chart(graf_totales, use_container_width=True)

    st.subheader("Detalle del histórico")
    st.dataframe(df, use_container_width=True)


render_history()
