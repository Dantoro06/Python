import streamlit as st

st.set_page_config(
    page_title="Nueve11 Risk Monitor PRO",
    page_icon="📊",
    layout="wide",
)

st.title("Nueve11 Risk Monitor PRO — Dashboard Principal")
st.write(
    "Navega con el menú lateral para consultar el histórico, la última ejecución y los"
    " módulos avanzados del monitor de riesgo. Los datos se leen desde los archivos"
    " JSON y Excel generados por el motor de análisis, ubicados en la raíz del"
    " proyecto."
)

st.info(
    "Si un módulo muestra una advertencia de falta de datos, verifica que los archivos"
    " de entrada estén disponibles en esta carpeta antes de recargar la aplicación.",
    icon="ℹ️",
)
