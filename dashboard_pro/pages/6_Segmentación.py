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


REPORTE_PATH = DASHBOARD_DATA_DIR / "reporte_riesgo_multicuenta.json"
HISTORICO_PATH = DASHBOARD_DATA_DIR / "historico_riesgo_multicuenta.json"


def cargar_reporte(path: Path = REPORTE_PATH) -> Optional[Dict[str, Any]]:
    try:
        path = cargar_json("reporte_riesgo_multicuenta.json")
    except FileNotFoundError:
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
    try:
        path = cargar_json("historico_riesgo_multicuenta.json")
    except FileNotFoundError:
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
        def normalizar_fecha(valor):
            try:
                fecha = pd.Timestamp(valor)
                if fecha.tzinfo is not None:
                    fecha = fecha.tz_localize(None)
                return fecha
            except (TypeError, ValueError, OverflowError):
                return pd.NaT

        df_hist["fecha_ejecucion"] = df_hist["fecha_ejecucion"].map(normalizar_fecha)
    return df_hist


def render_segmentation_view():
    st.set_page_config(page_title="Risk Monitor PRO — Segmentación")
    st.title("Risk Monitor PRO — Segmentación")

    report = cargar_reporte()
    historico_df = cargar_historico()

    if historico_df.empty:
        st.warning(
            "No hay histórico disponible para segmentar. Ejecuta el motor para generar "
            "Data Dashboard/historico_riesgo_multicuenta.json."
        )
    else:
        st.subheader("Evolución de casos por tipo")
        if {"total_casos_multi", "total_casos_self"}.issubset(historico_df.columns):
            melted = historico_df.melt(
                id_vars=["fecha_ejecucion"],
                value_vars=["total_casos_multi", "total_casos_self"],
                var_name="tipo",
                value_name="casos",
            )
            zoom_casos = alt.selection_interval(bind="scales", encodings=["x"])
            melted_visual = melted.copy()
            melted_visual["tipo"] = melted_visual["tipo"].replace({
                "total_casos_multi": "Casos Multi-Cuenta",
                "total_casos_self": "Casos Self-Hedging",
            })
            chart = (
                alt.Chart(melted_visual)
                .mark_line(point=True)
                .encode(
                    x=alt.X("fecha_ejecucion:T", title="Fecha de ejecución"),
                    y=alt.Y("casos:Q", title="Casos"),
                    color=alt.Color(
                        "tipo:N",
                        scale=alt.Scale(
                            domain=["Casos Multi-Cuenta", "Casos Self-Hedging"],
                            range=["#1f77b4", "#ff7f0e"],
                        ),
                        title="Riesgo detectado",
                    ),
                    tooltip=[
                        alt.Tooltip("fecha_ejecucion:T", title="Fecha de ejecución"),
                        alt.Tooltip("tipo:N", title="Tipo"),
                        alt.Tooltip("casos:Q", title="Casos"),
                    ],
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
                    x=alt.X("fecha_ejecucion:T", title="Fecha de ejecución"),
                    y=alt.Y("ratio_sospecha_global:Q", title="Ratio de sospecha global"),
                    tooltip=[
                        alt.Tooltip("fecha_ejecucion:T", title="Fecha de ejecución"),
                        alt.Tooltip("ratio_sospecha_global:Q", title="Ratio de sospecha global"),
                    ],
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
    etiquetas_parametros = {
        "tolerancia_cobertura": "Tolerancia de cobertura",
        "min_total_apostado": "Mínimo total apostado",
        "max_apuestas_por_seleccion": "Máximo de apuestas por selección",
        "ratio_min_margen": "Ratio mínimo de margen",
        "ratio_max_margen": "Ratio máximo de margen",
        "tol_abs": "Tolerancia absoluta",
        "k": "Factor K",
        "tol_max": "Tolerancia máxima",
        "modo_tolerancia": "Modo de tolerancia",
    }
    parametros_visual = pd.DataFrame(
        [(etiquetas_parametros.get(clave, clave), valor) for clave, valor in params.items()],
        columns=["Parámetro", "Valor"],
        dtype=object,
    )
    parametros_visual = parametros_visual.where(parametros_visual.notna(), "—")
    st.dataframe(parametros_visual, use_container_width=True)


render_segmentation_view()
