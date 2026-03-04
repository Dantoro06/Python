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
            "No hay reporte disponible en reports/reporte_riesgo_hiddingbonus.json. Ejecuta "
            "el motor para generarlo."
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
        st.error("El archivo de reporte no tiene un formato JSON válido.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer el reporte: {exc}")
    return None


def render_user_ranking(df: pd.DataFrame):
    st.subheader("Top usuarios por casos detectados")
    st.dataframe(df, use_container_width=True)


def render_user_panel(df: pd.DataFrame):
    st.subheader("Panel por usuario")
    if df.empty:
        st.info("El reporte no incluye información de usuarios.")
        return

    usuarios = df["Usuario"].tolist()
    seleccionado = st.selectbox("Selecciona un usuario", usuarios)
    detalle = df[df["Usuario"] == seleccionado].iloc[0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Casos totales", detalle.get("Casos totales", 0))
    col2.metric("Multiusuario", detalle.get("Multiusuario", 0))
    col3.metric("Self-hedging", detalle.get("Self-hedging", 0))
    col4.metric("Eventos", detalle.get("Eventos", 0))

    tipos = detalle.get("Tipos de riesgo")
    if isinstance(tipos, list):
        st.caption("Tipos de riesgo: " + ", ".join(tipos))
    else:
        st.caption("Sin detalle de tipos de riesgo")


def render_users_view():
    st.title("🧑‍💻 Usuarios Sospechosos — Análisis PRO")

    report = cargar_reporte()
    if not report:
        return

    if not isinstance(report, dict):
        st.error("El reporte no tiene el formato esperado (dict).")
        return

    usuarios_lista = report.get("top_usuarios_riesgo", [])
    if not usuarios_lista:
        st.info("El JSON no contiene ranking de usuarios.")
        return

    usuarios_df = pd.DataFrame(usuarios_lista)

    usuarios_df = usuarios_df.rename(
        columns={
            "usuario_id": "Usuario",
            "casos_total": "Casos totales",
            "casos_multiusuario": "Multiusuario",
            "casos_self_hedging": "Self-hedging",
            "eventos_involucrados": "Eventos",
            "tipos_riesgo": "Tipos de riesgo",
        }
    )

    render_user_ranking(usuarios_df)
    render_user_panel(usuarios_df)


render_users_view()
