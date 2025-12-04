import streamlit as st, pandas as pd, json, os
st.title("📈 Histórico de Riesgo")
path="historico_riesgo_hiddingbonus.json"
if os.path.exists(path):
    data=json.load(open(path))
    df=pd.DataFrame(data.get("ejecuciones",[]))
    st.dataframe(df,use_container_width=True)
else: st.warning("No hay histórico.")