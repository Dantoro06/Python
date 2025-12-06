from pathlib import Path

import pandas as pd
import streamlit as st

st.title("🎯 Eventos Críticos — Análisis PRO")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "abuso_bonus_total.xlsx"


def load_abuse_data(path: Path):
    try:
        return pd.read_excel(path)
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer {path.name}: {exc}")
        return None


def render_event_summary(df: pd.DataFrame):
    if "event_name" not in df.columns:
        st.info("El archivo no contiene la columna event_name para agrupar eventos.")
        return

    df_ev = df["event_name"].value_counts().reset_index()
    df_ev.columns = ["Evento", "Casos"]
    st.subheader("Eventos con mayor concentración de abuso")
    st.dataframe(df_ev, use_container_width=True)


def render_events_view():
    if not DATA_PATH.exists():
        st.warning(
            "No hay archivo de abuso total. Coloca abuso_bonus_total.xlsx en la carpeta"
            " raíz y recarga la app."
        )
        return

    df = load_abuse_data(DATA_PATH)
    if df is None:
        return

    st.caption(f"Fuente: {DATA_PATH.name}")
    render_event_summary(df)


render_events_view()
