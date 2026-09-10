import sys
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

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


DATA_PATH = DASHBOARD_DATA_DIR / "pipeline_global.json"


def cargar_reporte(path: Path = DATA_PATH) -> Optional[List[Dict[str, Any]]]:
    try:
        path = cargar_json(path.name)
    except FileNotFoundError:
        st.warning(
            f"No se encontró {path.name}. Ejecuta el Pipeline AML v0 para generarlo."
        )
        return None

    try:
        with path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, list) or not all(isinstance(registro, dict) for registro in data):
            st.error(f"{path.name} debe ser un JSON con una lista de registros como objeto raíz.")
            return None
        return data
    except json.JSONDecodeError:
        st.error("El archivo de reporte no tiene un formato JSON válido.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer el reporte: {exc}")
    return None


def render_user_ranking(df: pd.DataFrame):
    st.subheader("Top usuarios por casos detectados")
    st.dataframe(df, use_container_width=True)


def render_user_panel(df: pd.DataFrame, df_detalle: pd.DataFrame):
    st.subheader("Panel por usuario")
    if df.empty:
        st.info("El reporte no incluye información de usuarios.")
        return

    usuarios = df["Usuario"].tolist()
    seleccionado = st.selectbox("Selecciona un usuario", usuarios)
    detalle = df[df["Usuario"] == seleccionado].iloc[0]

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Casos totales", detalle.get("Casos totales", 0))
    col2.metric("Multiusuario", detalle.get("Multiusuario", 0))
    col3.metric("Self-hedging", detalle.get("Self-hedging", 0))
    col4.metric("Bonus Abuse", detalle.get("Bonus Abuse", 0))
    col5.metric("Eventos", detalle.get("Eventos", 0))

    st.write("Nivel global:", detalle.get("Nivel global"))
    st.write("Score global:", detalle.get("Score global"))

    tipos = detalle.get("Tipos de riesgo")
    if isinstance(tipos, list):
        st.caption("Tipos de riesgo: " + ", ".join(tipos))
    else:
        st.caption("Sin detalle de tipos de riesgo")

    st.subheader("Detalle de detecciones del usuario")
    detecciones = df_detalle[
        df_detalle.get("user_id", pd.Series(index=df_detalle.index, dtype="object")) == seleccionado
    ]
    columnas = [
        columna for columna in ["motor", "nivel_riesgo", "score", "flags", "evidencia", "event_name", "fecha_bucket"]
        if columna in detecciones.columns
    ]
    st.dataframe(detecciones[columnas], use_container_width=True)


def construir_ranking(df_global: pd.DataFrame, df_detalle: pd.DataFrame) -> pd.DataFrame:
    global_usuarios = df_global.reindex(
        columns=["user_id", "nivel_riesgo", "score", "motor", "flags", "evidencia"]
    ).dropna(subset=["user_id"])
    detalle = df_detalle.reindex(columns=["user_id", "motor", "event_name"])
    conteos = detalle.groupby("user_id").agg(
        **{
            "Casos totales": ("motor", "size"),
            "Multiusuario": ("motor", lambda motores: motores.eq("multi_cuenta").sum()),
            "Self-hedging": ("motor", lambda motores: motores.eq("self_hedging").sum()),
            "Bonus Abuse": ("motor", lambda motores: motores.eq("bonus_abuse").sum()),
            "Eventos": ("event_name", "nunique"),
            "Tipos de riesgo": ("motor", lambda motores: motores.dropna().unique().tolist()),
        }
    )
    ranking = global_usuarios.merge(conteos, on="user_id", how="left")
    columnas_conteos = ["Casos totales", "Multiusuario", "Self-hedging", "Bonus Abuse", "Eventos"]
    ranking[columnas_conteos] = ranking[columnas_conteos].fillna(0).astype(int)
    ranking["Tipos de riesgo"] = ranking["Tipos de riesgo"].map(
        lambda tipos: tipos if isinstance(tipos, list) else []
    )
    ranking = ranking.rename(
        columns={"user_id": "Usuario", "nivel_riesgo": "Nivel global", "score": "Score global"}
    )
    ranking["_prioridad"] = ranking["Nivel global"].map(
        {"CRITICO": 4, "ALTO": 3, "MEDIO": 2, "BAJO": 1}
    ).fillna(0)
    ranking["_score_num"] = pd.to_numeric(ranking["Score global"], errors="coerce")
    ranking = ranking.sort_values(
        ["_prioridad", "Casos totales", "_score_num"], ascending=False, na_position="last"
    )
    return ranking[
        ["Usuario", *columnas_conteos, "Nivel global", "Score global", "Tipos de riesgo"]
    ].reset_index(drop=True)


def render_users_view():
    st.set_page_config(page_title="Risk Monitor PRO — Usuarios")
    st.title("Risk Monitor PRO — Usuarios")

    report = cargar_reporte()
    report_detalle = cargar_reporte(DASHBOARD_DATA_DIR / "pipeline_detalle.json")
    if report is None or report_detalle is None:
        return

    df_detalle = pd.DataFrame(report_detalle)
    usuarios_df = construir_ranking(pd.DataFrame(report), df_detalle)
    if usuarios_df.empty:
        st.info("El JSON no contiene ranking de usuarios.")
        return

    render_user_ranking(usuarios_df)
    render_user_panel(usuarios_df, df_detalle)


render_users_view()
