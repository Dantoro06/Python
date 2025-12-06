import json
from pathlib import Path

import pandas as pd
import streamlit as st

st.title("📈 Histórico de Riesgo")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "historico_riesgo_hiddingbonus.json"


def load_history(path: Path):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        st.error("El archivo de histórico no tiene un formato JSON válido.")
        return None


def render_history():
    if not DATA_PATH.exists():
        st.warning(
            "No hay histórico disponible. Coloca historico_riesgo_hiddingbonus.json en la"
            " carpeta raíz y recarga la app."
        )
        return

    data = load_history(DATA_PATH)
    if not data:
        return

    df = pd.DataFrame(data.get("ejecuciones", []))
    if df.empty:
        st.info("El histórico no contiene ejecuciones para mostrar.")
        return

    st.caption(f"Fuente: {DATA_PATH.name}")
    st.dataframe(df, use_container_width=True)


render_history()
