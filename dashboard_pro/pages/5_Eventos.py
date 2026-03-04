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


def render_events_view():
    st.title("🎯 Eventos Críticos — Análisis PRO")

    report = cargar_reporte()
    if not report:
        return

    eventos_df = pd.DataFrame(report.get("top_eventos_sospechosos", []))
    if eventos_df.empty:
        st.info("El JSON no contiene ranking de eventos.")
        return

    eventos_df = eventos_df.rename(
        columns={
            "evento_id": "Evento",
            "usuarios_involucrados": "Usuarios involucrados",
            "fuentes": "Fuentes",
            "riesgo_maximo": "Riesgo máximo",
        }
    )

    st.caption(f"Fuente: {DATA_PATH}")
    st.dataframe(eventos_df, use_container_width=True)


render_events_view()
