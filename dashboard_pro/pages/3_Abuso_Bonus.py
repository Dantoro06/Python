import streamlit as st, pandas as pd, altair as alt, os
st.title("🔥 Abuso de Bonus — Análisis Avanzado")
path="abuso_bonus_total.xlsx"
if os.path.exists(path):
    df=pd.read_excel(path)
    st.subheader("Tabla consolidada")
    st.dataframe(df,use_container_width=True)
    if "nivel_abuso" in df.columns:
        st.subheader("Distribución por nivel de abuso")
        df_lvl=df["nivel_abuso"].value_counts().reset_index()
        df_lvl.columns=["Nivel","Casos"]
        chart=alt.Chart(df_lvl).mark_bar().encode(x="Nivel:N", y="Casos:Q")
        st.altair_chart(chart,use_container_width=True)
    if {"monto_bono","ganancia_estimada"}.issubset(df.columns):
        st.subheader("Bono vs Ganancia Estimada")
        chart2=alt.Chart(df).mark_circle(size=80).encode(
            x="monto_bono:Q", y="ganancia_estimada:Q", color="nivel_abuso:N",
            tooltip=["user_id","monto_bono","ganancia_estimada","nivel_abuso"]
        )
        st.altair_chart(chart2,use_container_width=True)
else: st.warning("No se encontró abuso_bonus_total.xlsx")