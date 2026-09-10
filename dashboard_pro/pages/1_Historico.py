import sys
import os
import json
from pathlib import Path

import altair as alt
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

from utils.dashboard_riesgo import construir_reporte_riesgo_dict  # noqa: E402,F401

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


DATA_PATH = DASHBOARD_DATA_DIR / "historico_riesgo_multicuenta.json"


def cargar_historico(path: Path = DATA_PATH) -> pd.DataFrame:
    try:
        path = cargar_json("historico_riesgo_multicuenta.json")
    except FileNotFoundError:
        return pd.DataFrame()
    if not path.exists():
        return pd.DataFrame()

    try:
        with path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return pd.DataFrame()
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
            "No hay histórico disponible. Asegúrate de que Data Dashboard/historico_riesgo_multicuenta.json "
            "exista y vuelva a cargar la aplicación."
        )
        return

    st.caption(f"Fuente: {DATA_PATH}")

    if "ratio_sospecha_global" in df.columns:
        zoom_ratio = alt.selection_interval(bind="scales", encodings=["x"])
        graf_ratio = (
            alt.Chart(df)
            .mark_line(point=True)
            .encode(
                x=alt.X("fecha_ejecucion:T", title="Fecha"),
                y=alt.Y("ratio_sospecha_global:Q", title="Ratio de sospecha"),
                tooltip=["fecha_ejecucion:T", "ratio_sospecha_global:Q"],
            )
            .add_selection(zoom_ratio)
            .interactive()
        )
        st.subheader("Evolución del ratio de sospecha")
        st.altair_chart(graf_ratio, use_container_width=True)

    if {"transacciones_totales", "total_casos_multi", "total_casos_self"}.issubset(df.columns):
        st.subheader("Resumen de ejecuciones")
        zoom_totales = alt.selection_interval(bind="scales", encodings=["x"])
        graf_totales = (
            alt.Chart(df)
            .transform_fold(
                ["transacciones_totales", "total_casos_multi", "total_casos_self"],
                as_=["Indicador", "Valor"],
            )
            .mark_bar()
            .encode(
                x="fecha_ejecucion:T",
                y="Valor:Q",
                color="Indicador:N",
                tooltip=["fecha_ejecucion:T", "Indicador:N", "Valor:Q"],
            )
            .add_selection(zoom_totales)
            .interactive()
        )
        st.altair_chart(graf_totales, use_container_width=True)

    st.subheader("Detalle del histórico")
    st.dataframe(df, use_container_width=True)


render_history()
