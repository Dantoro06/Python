from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

st.title("📊 Segmentación de Usuarios — PRO")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "abuso_bonus_total.xlsx"


def load_abuse_data(path: Path):
    try:
        return pd.read_excel(path)
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer {path.name}: {exc}")
        return None


def render_segmentation(df: pd.DataFrame):
    required_cols = {"score_abuso", "monto_bono"}
    if not required_cols.issubset(df.columns):
        st.info(
            "El archivo no contiene las columnas necesarias (score_abuso, monto_bono) para"
            " segmentar usuarios."
        )
        return

    st.subheader("Segmentación básica por score vs monto bono")
    chart = (
        alt.Chart(df)
        .mark_circle(size=60)
        .encode(
            x="monto_bono:Q",
            y="score_abuso:Q",
            color="nivel_abuso:N",
            tooltip=["user_id", "score_abuso", "monto_bono", "nivel_abuso"],
        )
    )
    st.altair_chart(chart, use_container_width=True)


def render_segmentation_view():
    if not DATA_PATH.exists():
        st.warning(
            "No hay archivo para segmentar. Coloca abuso_bonus_total.xlsx en la carpeta"
            " raíz y recarga la app."
        )
        return

    df = load_abuse_data(DATA_PATH)
    if df is None:
        return

    st.caption(f"Fuente: {DATA_PATH.name}")
    render_segmentation(df)


render_segmentation_view()
