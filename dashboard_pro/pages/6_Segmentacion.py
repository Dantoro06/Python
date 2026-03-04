import sys
import os
import json
from pathlib import Path
from typing import Any, Dict, Optional

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

DASHBOARD_DATA_DIR = Path(PROJECT_ROOT) / "Data Dashboard"
DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = Path(PROJECT_ROOT) / "reports"


def _resolver_json(nombre: str) -> Path:
    primary = DASHBOARD_DATA_DIR / nombre
    if primary.exists():
        return primary
    return REPORTS_DIR / nombre


REPORTE_PATH = _resolver_json("reporte_riesgo_hiddingbonus.json")
HISTORICO_PATH = _resolver_json("historico_riesgo_hiddingbonus.json")


def cargar_reporte(path: Path = REPORTE_PATH) -> Optional[Dict[str, Any]]:
    path = _resolver_json("reporte_riesgo_hiddingbonus.json")
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            st.error("El reporte debe ser un JSON con objeto raíz (dict).")
            return None
        return data
    except json.JSONDecodeError:
        st.error("El archivo de reporte no tiene un formato JSON válido.")
    except Exception:  # noqa: BLE001
        return None


def cargar_historico(path: Path = HISTORICO_PATH) -> pd.DataFrame:
    path = _resolver_json("historico_riesgo_hiddingbonus.json")
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


def render_segmentation_view():
    st.title("📊 Segmentación de Riesgo — PRO")

    report = cargar_reporte()
    historico_df = cargar_historico()

    if historico_df.empty:
        st.warning(
            "No hay histórico disponible para segmentar. Ejecuta el motor para generar "
            "Data Dashboard/historico_riesgo_hiddingbonus.json."
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
            zoom_casos = alt.selection_interval(bind="scales", encodings=["x"])
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
                .add_selection(zoom_casos)
                .interactive()
            )
            st.altair_chart(chart, use_container_width=True)

        if "ratio_sospecha_global" in historico_df.columns:
            st.subheader("Ratio de sospecha global")
            zoom_ratio = alt.selection_interval(bind="scales", encodings=["x"])
            graf_ratio = (
                alt.Chart(historico_df)
                .mark_line(point=True)
                .encode(
                    x="fecha_ejecucion:T",
                    y="ratio_sospecha_global:Q",
                    tooltip=["fecha_ejecucion:T", "ratio_sospecha_global:Q"],
                )
                .add_selection(zoom_ratio)
                .interactive()
            )
            st.altair_chart(graf_ratio, use_container_width=True)

    st.subheader("Parámetros de la última ejecución")
    if not report:
        st.info("Aún no hay reporte actual para mostrar parámetros.")
        return

    params = report.get("parametros_motor", {})
    st.json(params, expanded=False)


render_segmentation_view()
