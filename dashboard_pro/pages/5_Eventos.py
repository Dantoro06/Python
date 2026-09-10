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


DATA_PATH = DASHBOARD_DATA_DIR / "pipeline_detalle.json"


def cargar_reporte(path: Path = DATA_PATH) -> Optional[List[Dict[str, Any]]]:
    try:
        path = cargar_json("pipeline_detalle.json")
    except FileNotFoundError:
        st.warning(
            "No se encontró pipeline_detalle.json. Ejecuta el Pipeline AML v0 para generarlo."
        )
        return None

    try:
        with path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, list) or not all(isinstance(registro, dict) for registro in data):
            st.error("El reporte debe ser un JSON con una lista de registros como objeto raíz.")
            return None
        return data
    except json.JSONDecodeError:
        st.error("El archivo de reporte no tiene un formato JSON válido.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer el reporte: {exc}")
    return None


def render_events_view():
    st.set_page_config(page_title="Risk Monitor PRO — Eventos")
    st.title("Risk Monitor PRO — Eventos")
    st.caption(f"Fuente: {DATA_PATH}")

    report = cargar_reporte()
    if report is None:
        return

    detecciones = pd.DataFrame(report).reindex(
        columns=["event_name", "fecha_bucket", "user_id", "motor", "nivel_riesgo", "evidencia"]
    )
    detecciones = detecciones[
        detecciones["event_name"].notna()
        & detecciones["event_name"].astype(str).str.strip().ne("")
    ]
    if detecciones.empty:
        st.info("El pipeline no contiene detecciones con evento.")
        return

    prioridad = {"CRITICO": 4, "ALTO": 3, "MEDIO": 2, "BAJO": 1}
    eventos_df = detecciones.groupby(["event_name", "fecha_bucket"], dropna=False).agg(
        **{
            "Usuarios involucrados": ("user_id", lambda usuarios: usuarios.dropna().unique().tolist()),
            "Cantidad usuarios": ("user_id", "nunique"),
            "Fuentes": ("motor", lambda motores: motores.dropna().unique().tolist()),
            "Riesgo máximo": (
                "nivel_riesgo",
                lambda niveles: max(
                    (nivel for nivel in niveles if nivel in prioridad),
                    key=prioridad.get,
                    default=None,
                ),
            ),
            "Evidencia": ("evidencia", lambda evidencias: evidencias.dropna().unique().tolist()),
        }
    ).reset_index()
    eventos_df = eventos_df.rename(
        columns={"event_name": "Evento", "fecha_bucket": "Fecha / bucket"}
    )
    eventos_df["_prioridad"] = eventos_df["Riesgo máximo"].map(prioridad).fillna(0)
    eventos_df["_fecha"] = eventos_df["Fecha / bucket"].map(
        lambda fecha: pd.to_datetime(fecha, errors="coerce", utc=True)
    )
    eventos_df = eventos_df.sort_values(
        ["_prioridad", "_fecha"], ascending=False, na_position="last"
    ).drop(columns=["_prioridad", "_fecha"]).reset_index(drop=True)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Eventos detectados", len(eventos_df))
    col2.metric("Usuarios involucrados", detecciones["user_id"].nunique(dropna=True))
    col3.metric(
        "Eventos Multi-Cuenta", eventos_df["Fuentes"].map(lambda fuentes: "multi_cuenta" in fuentes).sum()
    )
    col4.metric(
        "Eventos Self-Hedging", eventos_df["Fuentes"].map(lambda fuentes: "self_hedging" in fuentes).sum()
    )

    st.dataframe(eventos_df, use_container_width=True)


render_events_view()
