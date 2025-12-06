import sys
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import altair as alt
import pandas as pd
import streamlit as st

# FIX de rutas (equivalente a app_hidding_bonus_tk.py)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.dashboard_riesgo import construir_reporte_riesgo_dict  # noqa: E402,F401

REPORTS_DIR = (
    Path(PROJECT_ROOT) / "reports"
    if (Path(PROJECT_ROOT) / "reports").exists()
    else Path(BASE_DIR) / "reports"
)
REPORTE_PATH = REPORTS_DIR / "reporte_riesgo_hiddingbonus.json"
HISTORICO_PATH = REPORTS_DIR / "historico_riesgo_hiddingbonus.json"


def cargar_reporte_reciente(path: Path = REPORTE_PATH) -> Optional[Dict[str, Any]]:
    """Carga el reporte actual generado por el motor."""
    if not path.exists():
        st.warning(
            "No se encontró el archivo de reporte reciente. Ejecuta el motor para generar "
            "reporte_riesgo_hiddingbonus.json en la carpeta reports/."
        )
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        st.error("El archivo de reporte no contiene JSON válido.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer el reporte: {exc}")
    return None


def cargar_historico(path: Path = HISTORICO_PATH) -> pd.DataFrame:
    """Carga el histórico de ejecuciones desde reports/."""
    if not path.exists():
        return pd.DataFrame()

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()

    ejecuciones = data.get("ejecuciones", [])
    if not ejecuciones:
        return pd.DataFrame()

    df_hist = pd.DataFrame(ejecuciones)
    if "fecha_ejecucion" in df_hist.columns:
        df_hist["fecha_ejecucion"] = pd.to_datetime(
            df_hist["fecha_ejecucion"], errors="coerce"
        )
    return df_hist


def _crear_df_niveles(estadisticas: Dict[str, Any], clave: str) -> pd.DataFrame:
    datos = estadisticas.get(clave, {}) or {}
    conteos = datos.get("por_nivel", {}) if isinstance(datos, dict) else {}
    niveles = [
        {"Nivel": nivel, "Casos": conteos.get(nivel, 0)}
        for nivel in ["ALTO", "MEDIO", "BAJO"]
    ]
    return pd.DataFrame(niveles)


def _kpi_value(valor: Any, default: Any = 0) -> Any:
    return valor if valor not in (None, "") else default


def _fuente_reporte(uploaded_file) -> Optional[Dict[str, Any]]:
    """Selecciona el JSON ya cargado o uno subido manualmente."""
    if uploaded_file is None:
        return cargar_reporte_reciente()

    try:
        data = json.load(uploaded_file)
        st.success("Archivo JSON cargado manualmente.")
        return data
    except json.JSONDecodeError:
        st.error("El archivo subido no es un JSON válido.")
    return None


def _tabla_top(datos: List[Dict[str, Any]], columnas: Dict[str, str]) -> pd.DataFrame:
    if not datos:
        return pd.DataFrame()
    df = pd.DataFrame(datos)
    if columnas:
        df = df.rename(columns=columnas)
    return df


def _panel_usuario(detalle: Dict[str, Any]) -> None:
    st.markdown("### Explorador de riesgo por usuario")
    if not detalle:
        st.info("No hay información de usuarios en el JSON de reporte.")
        return

    usuarios = [d.get("usuario_id") for d in detalle if d.get("usuario_id")]
    if not usuarios:
        st.info("No se encontraron usuarios identificados.")
        return

    seleccionado = st.selectbox("Selecciona un usuario", usuarios)
    usuario_data = next((d for d in detalle if d.get("usuario_id") == seleccionado), None)
    if not usuario_data:
        st.warning("No hay detalles para el usuario seleccionado.")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Casos totales", usuario_data.get("casos_total", 0))
    col2.metric("Multiusuario", usuario_data.get("casos_multiusuario", 0))
    col3.metric("Self-hedging", usuario_data.get("casos_self_hedging", 0))
    col4.metric(
        "Eventos involucrados", usuario_data.get("eventos_involucrados", 0)
    )

    tipos = usuario_data.get("tipos_riesgo", [])
    st.caption(
        "Tipos de riesgo detectados: "
        + ", ".join(tipos)
        if tipos
        else "Sin categorías especificadas"
    )


st.set_page_config(
    page_title="Nueve11 Risk Monitor PRO",
    page_icon="📊",
    layout="wide",
)

st.title("Nueve11 Risk Monitor PRO — Dashboard Principal")
st.caption(
    "Panel oficial conectado al motor de riesgo. Usa los reportes JSON generados por "
    "el proceso de análisis sin replicar la lógica del motor."
)

cargador_manual = st.sidebar.file_uploader(
    "Cargar un reporte JSON manual (opcional)", type=["json"]
)
reporte = _fuente_reporte(cargador_manual)

if not reporte:
    st.stop()

historico_df = cargar_historico()
resumen = reporte.get("resumen_ejecucion", {})
meta = reporte.get("metadata", {})
estadisticas = reporte.get("estadisticas_riesgo", {})

st.subheader("Overview")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total transacciones", f"{_kpi_value(resumen.get('total_transacciones'), 0):,}".replace(",", "."))
col2.metric("Usuarios analizados", _kpi_value(resumen.get("usuarios_analizados"), 0))
col3.metric("Eventos analizados", _kpi_value(resumen.get("eventos_analizados"), 0))
ratio_global = float(_kpi_value(resumen.get("ratio_sospecha_global"), 0.0)) * 100
col4.metric("Ratio sospecha global", f"{ratio_global:.2f}%")

col5, col6, col7, col8 = st.columns(4)
col5.metric("Casos multiusuario", _kpi_value(estadisticas.get("multiusuario", {}).get("casos_totales"), 0))
col6.metric("Casos self-hedging", _kpi_value(estadisticas.get("self_hedging", {}).get("casos_totales"), 0))
col7.metric("Archivos analizados", len(meta.get("archivos_procesados", []) or []))
col8.metric("Duración (seg)", _kpi_value(resumen.get("tiempo_proceso_seg"), 0))

st.markdown(
    f"**Fecha de ejecución:** {meta.get('fecha_ejecucion', '—')} · "
    f"**Servidor:** {meta.get('servidor', '—')}"
)

st.markdown("---")
st.subheader("Riesgo Global")

niveles_multi = _crear_df_niveles(estadisticas, "multiusuario")
niveles_self = _crear_df_niveles(estadisticas, "self_hedging")

col_a, col_b = st.columns(2)
with col_a:
    st.caption("Distribución de riesgo — Multiusuario")
    chart_multi = (
        alt.Chart(niveles_multi)
        .mark_bar(color="#1f77b4")
        .encode(x="Nivel:N", y="Casos:Q", tooltip=["Nivel", "Casos"])
    )
    st.altair_chart(chart_multi, use_container_width=True)

with col_b:
    st.caption("Distribución de riesgo — Self-hedging")
    chart_self = (
        alt.Chart(niveles_self)
        .mark_bar(color="#ff7f0e")
        .encode(x="Nivel:N", y="Casos:Q", tooltip=["Nivel", "Casos"])
    )
    st.altair_chart(chart_self, use_container_width=True)

st.markdown("---")
st.subheader("Multiusuario")
st.write("Casos detectados y severidad según el reporte del motor.")
st.dataframe(niveles_multi, use_container_width=True)

st.subheader("Self-Hedging")
st.write("Resumen de casos de cobertura sospechosa.")
st.dataframe(niveles_self, use_container_width=True)

st.markdown("---")
st.subheader("Top Usuarios")
usuarios_df = _tabla_top(
    reporte.get("top_usuarios_riesgo", []),
    {
        "usuario_id": "Usuario",
        "casos_total": "Casos totales",
        "casos_multiusuario": "Multiusuario",
        "casos_self_hedging": "Self-hedging",
        "eventos_involucrados": "Eventos",
        "tipos_riesgo": "Tipos de riesgo",
    },
)
if usuarios_df.empty:
    st.info("El reporte no incluye ranking de usuarios.")
else:
    st.dataframe(usuarios_df, use_container_width=True)

st.markdown("---")
st.subheader("Top Eventos")
eventos_df = _tabla_top(
    reporte.get("top_eventos_sospechosos", []),
    {
        "evento_id": "Evento",
        "usuarios_involucrados": "Usuarios involucrados",
        "fuentes": "Fuentes",
        "riesgo_maximo": "Riesgo máximo",
    },
)
if eventos_df.empty:
    st.info("El reporte no incluye ranking de eventos.")
else:
    st.dataframe(eventos_df, use_container_width=True)

st.markdown("---")
st.subheader("Histórico")
if historico_df.empty:
    st.warning(
        "No hay histórico disponible. Ejecuta el motor al menos una vez para generar "
        "reports/historico_riesgo_hiddingbonus.json."
    )
else:
    graf_ratio = (
        alt.Chart(historico_df)
        .mark_line(point=True)
        .encode(
            x=alt.X("fecha_ejecucion:T", title="Fecha"),
            y=alt.Y("ratio_sospecha_global:Q", title="Ratio sospecha"),
            tooltip=["fecha_ejecucion:T", "ratio_sospecha_global:Q"],
        )
    )
    st.altair_chart(graf_ratio, use_container_width=True)
    st.dataframe(historico_df, use_container_width=True)

st.markdown("---")
_panel_usuario(reporte.get("top_usuarios_riesgo", []))
