import streamlit as st, pandas as pd, altair as alt, os
st.title("📊 Segmentación de Usuarios — PRO")
path="abuso_bonus_total.xlsx"
if os.path.exists(path):
    df=pd.read_excel(path)
    if {"score_abuso","monto_bono"}.issubset(df.columns):
        st.subheader("Segmentación básica por score vs monto bono")
        chart=alt.Chart(df).mark_circle(size=60).encode(
            x="monto_bono:Q", y="score_abuso:Q", color="nivel_abuso:N",
            tooltip=["user_id","score_abuso","monto_bono","nivel_abuso"]
        )
        st.altair_chart(chart,use_container_width=True)
else: st.warning("No hay archivo para segmentar.")