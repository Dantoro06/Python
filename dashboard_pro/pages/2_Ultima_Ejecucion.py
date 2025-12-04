import streamlit as st, json, os
st.title("🔍 Última Ejecución")
path="reporte_riesgo_hiddingbonus.json"
if os.path.exists(path):
    st.json(json.load(open(path)))
else: st.warning("No hay reporte actual.")