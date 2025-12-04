import streamlit as st, pandas as pd, os
st.title("🧑‍💻 Usuarios Sospechosos — Análisis PRO")
path="abuso_bonus_total.xlsx"
if os.path.exists(path):
    df=pd.read_excel(path)
    st.subheader("Ranking de usuarios por score")
    if {"user_id","score_abuso"}.issubset(df.columns):
        df_rank=df.groupby("user_id")["score_abuso"].sum().reset_index()
        df_rank=df_rank.sort_values("score_abuso",ascending=False)
        st.dataframe(df_rank,use_container_width=True)
else: st.warning("No hay archivo de abuso total.")