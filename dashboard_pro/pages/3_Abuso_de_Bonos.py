import sys
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

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


DATA_PATH = DASHBOARD_DATA_DIR / "pipeline_detalle.json"


def cargar_reporte(path: Path = DATA_PATH) -> Optional[List[Dict[str, Any]]]:
    try:
        path = cargar_json("pipeline_detalle.json")
    except FileNotFoundError:
        st.warning(
            "No se encontró pipeline_detalle.json. Ejecuta el Pipeline AML v0 para generarlo."
        )
        return None
    if not path.exists():
        st.warning(
            "No se encontró pipeline_detalle.json. Ejecuta el Pipeline AML v0 para generarlo."
        )
        return None

    try:
        with path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, list):
            st.error("El reporte debe ser un JSON con una lista de registros como objeto raíz.")
            return None
        return data
    except json.JSONDecodeError:
        st.error("El archivo de reporte no contiene JSON válido.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer el reporte: {exc}")
    return None


def _df_niveles(df: pd.DataFrame) -> pd.DataFrame:
    conteos = df.get("nivel_riesgo", pd.Series(dtype="object")).value_counts()
    return pd.DataFrame(
        [
            {"Nivel": nivel, "Casos": conteos.get(nivel, 0)}
            for nivel in ["CRITICO", "ALTO", "MEDIO", "BAJO"]
        ]
    )


def _indicadores_visuales(valor):
    if not isinstance(valor, str):
        return valor
    etiquetas = {
        "bonus_abuse": "Abuso de Bonos",
        "ratio_alto": "Ratio alto",
        "retiro_rapido": "Retiro rápido",
        "frecuencia_alta": "Frecuencia alta",
    }
    return " · ".join(etiquetas.get(indicador.strip(), indicador) for indicador in valor.split("|"))


def _tabla_visual(df: pd.DataFrame) -> pd.DataFrame:
    return df.astype(object).where(df.notna(), "—")


def render_abuse_view():
    st.set_page_config(page_title="Risk Monitor PRO — Abuso de Bonos")
    st.title("Risk Monitor PRO — Abuso de Bonos")
    st.caption(f"Fuente: {DATA_PATH}")

    report = cargar_reporte()
    if report is None:
        return

    detecciones = [
        registro for registro in report
        if isinstance(registro, dict) and registro.get("motor") == "bonus_abuse"
    ]
    if not detecciones:
        st.info("No hay detecciones de Bonus Abuse en pipeline_detalle.json.")
        return

    df = pd.DataFrame(detecciones)
    usuarios = df.get("user_id", pd.Series(dtype="object")).nunique(dropna=True)
    scores = pd.to_numeric(df.get("score", pd.Series(dtype="object")), errors="coerce").dropna()
    score_promedio = scores.mean() if not scores.empty else 0
    score_maximo = scores.max() if not scores.empty else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Casos detectados", len(df))
    col2.metric("Usuarios detectados", usuarios)
    col3.metric("Score promedio", f"{score_promedio:.2f}")
    col4.metric("Score máximo", score_maximo)

    st.subheader("Distribución por nivel de riesgo")
    niveles_df = _df_niveles(df)
    chart = alt.Chart(niveles_df).mark_bar(color="#1f77b4").encode(
        x=alt.X("Nivel:N", sort=["CRITICO", "ALTO", "MEDIO", "BAJO"]),
        y="Casos:Q",
        tooltip=["Nivel", "Casos"],
    )
    st.altair_chart(chart, use_container_width=True)
    st.dataframe(_tabla_visual(niveles_df), use_container_width=True)

    st.subheader("Detalle de detecciones")
    columnas = [
        columna for columna in ["user_id", "nivel_riesgo", "score", "flags", "evidencia"]
        if columna in df.columns
    ]
    detalle_visual = df[columnas].copy()
    if "flags" in detalle_visual.columns:
        detalle_visual["flags"] = detalle_visual["flags"].map(_indicadores_visuales)
    detalle_visual = detalle_visual.rename(columns={
        "user_id": "Usuario",
        "nivel_riesgo": "Nivel de riesgo",
        "score": "Puntaje de riesgo",
        "flags": "Indicadores",
        "evidencia": "Evidencia",
    })
    st.dataframe(_tabla_visual(detalle_visual), use_container_width=True)


render_abuse_view()
