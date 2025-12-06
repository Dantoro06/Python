from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

st.title("🔥 Abuso de Bonus — Análisis Avanzado")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "abuso_bonus_total.xlsx"


def load_abuse_data(path: Path):
    try:
        return pd.read_excel(path)
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer {path.name}: {exc}")
        return None


def render_tables(df: pd.DataFrame):
    st.subheader("Tabla consolidada")
    st.dataframe(df, use_container_width=True)


def render_level_distribution(df: pd.DataFrame):
    if "nivel_abuso" not in df.columns:
        return

    st.subheader("Distribución por nivel de abuso")
    df_lvl = df["nivel_abuso"].value_counts().reset_index()
    df_lvl.columns = ["Nivel", "Casos"]
    chart = alt.Chart(df_lvl).mark_bar().encode(x="Nivel:N", y="Casos:Q")
    st.altair_chart(chart, use_container_width=True)


def render_bonus_vs_gain(df: pd.DataFrame):
    required_cols = {"monto_bono", "ganancia_estimada"}
    if not required_cols.issubset(df.columns):
        return

    st.subheader("Bono vs Ganancia Estimada")
    chart = (
        alt.Chart(df)
        .mark_circle(size=80)
        .encode(
            x="monto_bono:Q",
            y="ganancia_estimada:Q",
            color="nivel_abuso:N",
            tooltip=["user_id", "monto_bono", "ganancia_estimada", "nivel_abuso"],
        )
    )
    st.altair_chart(chart, use_container_width=True)


def render_abuse_view():
    if not DATA_PATH.exists():
        st.warning(
            "No se encontró abuso_bonus_total.xlsx en la carpeta raíz. Agrega el archivo"
            " y recarga la app."
        )
        return

    df = load_abuse_data(DATA_PATH)
    if df is None:
        return

    st.caption(f"Fuente: {DATA_PATH.name}")
    render_tables(df)
    render_level_distribution(df)
    render_bonus_vs_gain(df)


render_abuse_view()
