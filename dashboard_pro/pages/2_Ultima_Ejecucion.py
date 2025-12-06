import json
from pathlib import Path

import streamlit as st

st.title("🔍 Última Ejecución")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "reporte_riesgo_hiddingbonus.json"


def load_report(path: Path):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        st.error("El reporte actual no tiene un formato JSON válido.")
        return None


def render_last_run():
    if not DATA_PATH.exists():
        st.warning(
            "No hay reporte actual. Coloca reporte_riesgo_hiddingbonus.json en la carpeta"
            " raíz y recarga la app."
        )
        return

    report = load_report(DATA_PATH)
    if report:
        st.caption(f"Fuente: {DATA_PATH.name}")
        st.json(report)


render_last_run()
