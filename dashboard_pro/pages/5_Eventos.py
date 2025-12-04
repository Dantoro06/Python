import streamlit as st, pandas as pd, os
st.title("🎯 Eventos Críticos — Análisis PRO")
path="abuso_bonus_total.xlsx"
if os.path.exists(path):
    df=pd.read_excel(path)
    st.subheader("Eventos con mayor concentración de abuso")
    if "event_name" in df.columns:
        df_ev=df["event_name"].value_counts().reset_index()
        df_ev.columns=["Evento","Casos"]
        st.dataframe(df_ev,use_container_width=True)
else: st.warning("No hay archivo de abuso total.")