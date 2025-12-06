from pathlib import Path

import pandas as pd
import streamlit as st

st.title("🧑‍💻 Usuarios Sospechosos — Análisis PRO")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "abuso_bonus_total.xlsx"


def load_abuse_data(path: Path):
    try:
        return pd.read_excel(path)
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer {path.name}: {exc}")
        return None


def render_user_ranking(df: pd.DataFrame):
    required_cols = {"user_id", "score_abuso"}
    if not required_cols.issubset(df.columns):
        st.info(
            "El archivo no contiene las columnas necesarias (user_id, score_abuso) para"
            " construir el ranking."
        )
        return

    df_rank = df.groupby("user_id")["score_abuso"].sum().reset_index()
    df_rank = df_rank.sort_values("score_abuso", ascending=False)
    st.subheader("Ranking de usuarios por score")
    st.dataframe(df_rank, use_container_width=True)


def render_users_view():
    if not DATA_PATH.exists():
        st.warning(
            "No hay archivo de abuso_total. Coloca abuso_bonus_total.xlsx en la carpeta"
            " raíz y recarga la app."
        )
        return

    df = load_abuse_data(DATA_PATH)
    if df is None:
        return

    st.caption(f"Fuente: {DATA_PATH.name}")
    render_user_ranking(df)


render_users_view()
