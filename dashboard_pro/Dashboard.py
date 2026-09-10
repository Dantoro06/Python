import sys
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Inserta Motor Riesgo/src en sys.path (resolviendo desde este archivo)
_DASHBOARD_DIR = Path(__file__).resolve().parent
_SRC_FIX = _DASHBOARD_DIR.parent / "src"
if str(_SRC_FIX) not in sys.path:
    sys.path.insert(0, str(_SRC_FIX))

# === HABILITAR IMPORTS DESDE src/ ===
# === HABILITAR IMPORTS DESDE src/ ===
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import altair as alt
import pandas as pd
import streamlit as st

# FIX de rutas (equivalente a app_hidding_bonus_tk.py)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


try:
    from src.utils.paths_dashboard import DASHBOARD_DATA_DIR, REPORTS_DIR
except Exception:
    from utils.paths_dashboard import DASHBOARD_DATA_DIR, REPORTS_DIR


def cargar_json(nombre: str) -> Path:
    p1 = DASHBOARD_DATA_DIR / nombre
    p2 = REPORTS_DIR / nombre
    if p1.exists():
        return p1
    if p2.exists():
        return p2
    raise FileNotFoundError(
        f"No se encontro '{nombre}' en '{DASHBOARD_DATA_DIR}' ni en '{REPORTS_DIR}'."
    )


REPORTE_PATH = DASHBOARD_DATA_DIR / "reporte_riesgo_multicuenta.json"
HISTORICO_PATH = DASHBOARD_DATA_DIR / "historico_riesgo_multicuenta.json"
PRIORIDAD_RIESGO = {"CRITICO": 4, "ALTO": 3, "MEDIO": 2, "BAJO": 1}


def _leer_json(nombre: str, tipo):
    try:
        path = cargar_json(nombre)
        with path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, tipo):
        return None
    if tipo is list and not all(isinstance(registro, dict) for registro in data):
        return None
    return data


def cargar_reporte_reciente(path: Path = REPORTE_PATH) -> Optional[Dict[str, Any]]:
    return _leer_json(path.name, dict)


def _fecha_local(valor):
    try:
        fecha = pd.Timestamp(valor)
        return fecha.tz_localize(None) if fecha.tzinfo is not None else fecha
    except (TypeError, ValueError, OverflowError):
        return pd.NaT


def cargar_historico(path: Path = HISTORICO_PATH) -> Optional[pd.DataFrame]:
    data = _leer_json(path.name, dict)
    if data is None or not isinstance(data.get("ejecuciones"), list):
        return None
    if not all(isinstance(registro, dict) for registro in data["ejecuciones"]):
        return None
    df_hist = pd.DataFrame(data["ejecuciones"])
    if "fecha_ejecucion" in df_hist.columns:
        df_hist["fecha_ejecucion"] = df_hist["fecha_ejecucion"].map(_fecha_local)
    return df_hist


def cargar_pipeline_global() -> Optional[List[Dict[str, Any]]]:
    return _leer_json("pipeline_global.json", list)


def cargar_pipeline_detalle() -> Optional[List[Dict[str, Any]]]:
    return _leer_json("pipeline_detalle.json", list)


def cargar_aml_pipeline() -> Optional[Dict[str, Any]]:
    return _leer_json("aml_pipeline.json", dict)


def _aviso_fuente(nombre: str):
    st.info(f"No hay una fuente válida disponible: {nombre}. Ejecuta el proceso correspondiente para generarla.")


def _kpi_value(valor: Any, default: Any = 0) -> Any:
    return valor if valor not in (None, "") else default


def _usuarios_globales(registros: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(registros).reindex(columns=["user_id", "motor", "nivel_riesgo", "score", "flags"])
    df = df.dropna(subset=["user_id"])
    df["_prioridad"] = df["nivel_riesgo"].map(PRIORIDAD_RIESGO).fillna(0)
    df["_score_num"] = pd.to_numeric(df["score"], errors="coerce")
    return df.sort_values(
        ["_prioridad", "_score_num"], ascending=False, na_position="last"
    ).drop(columns=["_prioridad", "_score_num"]).reset_index(drop=True)


def _eventos_riesgo(registros: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(registros).reindex(
        columns=["event_name", "fecha_bucket", "user_id", "motor", "nivel_riesgo"]
    )
    df = df[df["event_name"].notna() & df["event_name"].astype(str).str.strip().ne("")]
    if df.empty:
        return pd.DataFrame()
    eventos = df.groupby(["event_name", "fecha_bucket"], dropna=False).agg(
        **{
            "Usuarios involucrados": ("user_id", lambda valores: valores.dropna().unique().tolist()),
            "Cantidad usuarios": ("user_id", "nunique"),
            "Fuentes": ("motor", lambda valores: valores.dropna().unique().tolist()),
            "Riesgo máximo": (
                "nivel_riesgo",
                lambda niveles: max(
                    (nivel for nivel in niveles if nivel in PRIORIDAD_RIESGO),
                    key=PRIORIDAD_RIESGO.get,
                    default=None,
                ),
            ),
        }
    ).reset_index().rename(columns={"event_name": "Evento", "fecha_bucket": "Fecha / bucket"})
    eventos["_prioridad"] = eventos["Riesgo máximo"].map(PRIORIDAD_RIESGO).fillna(0)
    eventos["_fecha"] = eventos["Fecha / bucket"].map(_fecha_local)
    return eventos.sort_values(
        ["_prioridad", "_fecha"], ascending=False, na_position="last"
    ).drop(columns=["_prioridad", "_fecha"]).reset_index(drop=True)


def _panel_usuario(usuarios: Optional[pd.DataFrame], registros: Optional[List[Dict[str, Any]]]) -> None:
    st.markdown("### Explorador de riesgo por usuario")
    if usuarios is None:
        _aviso_fuente("pipeline_global.json")
        return
    if usuarios.empty:
        st.info("No se encontraron usuarios identificados.")
        return
    seleccionado = st.selectbox("Selecciona un usuario", usuarios["user_id"].unique().tolist())
    usuario = usuarios[usuarios["user_id"] == seleccionado].iloc[0]
    col1, col2, col3 = st.columns(3)
    col1.metric("Nivel global", _kpi_value(usuario.get("nivel_riesgo"), "—"))
    col2.metric("Score global", _kpi_value(usuario.get("score"), "—"))
    col3.metric("Motor principal", _kpi_value(usuario.get("motor"), "—"))
    if registros is None:
        _aviso_fuente("pipeline_detalle.json")
        return
    detalle = pd.DataFrame(registros)
    detalle = detalle[
        detalle.get("user_id", pd.Series(index=detalle.index, dtype="object")) == seleccionado
    ]
    eventos = detalle.get("event_name", pd.Series(dtype="object")).dropna()
    eventos = eventos[eventos.astype(str).str.strip().ne("")]
    col1, col2 = st.columns(2)
    col1.metric("Detecciones totales", len(detalle))
    col2.metric("Eventos únicos", eventos.nunique())
    columnas = [
        columna for columna in ["motor", "nivel_riesgo", "score", "flags", "evidencia", "event_name", "fecha_bucket"]
        if columna in detalle.columns
    ]
    st.dataframe(detalle[columnas], use_container_width=True)


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

reporte = cargar_reporte_reciente()
historico_df = cargar_historico()
global_registros = cargar_pipeline_global()
detalle_registros = cargar_pipeline_detalle()
aml = cargar_aml_pipeline()
usuarios_df = _usuarios_globales(global_registros) if global_registros is not None else None

st.subheader("Overview")
if reporte is None:
    _aviso_fuente("reporte_riesgo_multicuenta.json")
else:
    resumen = reporte.get("resumen_ejecucion", {}) or {}
    meta = reporte.get("metadata", {}) or {}
    estadisticas = reporte.get("estadisticas_riesgo", {}) or {}
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Transacciones analizadas 1X2", f"{_kpi_value(resumen.get('total_transacciones'), 0):,}".replace(",", "."))
    col2.metric("Usuarios analizados 1X2", _kpi_value(resumen.get("usuarios_analizados"), 0))
    col3.metric("Eventos analizados 1X2", _kpi_value(resumen.get("eventos_analizados"), 0))
    ratio_global = float(_kpi_value(resumen.get("ratio_sospecha_global"), 0.0)) * 100
    col4.metric("Ratio sospecha 1X2", f"{ratio_global:.2f}%")

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Casos Multi-Cuenta", _kpi_value((estadisticas.get("multiusuario") or {}).get("casos_totales"), 0))
    col6.metric("Casos Self-Hedging", _kpi_value((estadisticas.get("self_hedging") or {}).get("casos_totales"), 0))
    col7.metric(
        "Casos Bonus Abuse",
        sum(registro.get("motor") == "bonus_abuse" for registro in detalle_registros)
        if detalle_registros is not None else "—",
    )
    col8.metric("Usuarios con detección", usuarios_df["user_id"].nunique() if usuarios_df is not None else "—")
    if detalle_registros is None:
        _aviso_fuente("pipeline_detalle.json")
    if usuarios_df is None:
        _aviso_fuente("pipeline_global.json")

    metadata_visible = []
    for etiqueta, valor in [
        ("Fecha de ejecución", meta.get("fecha_ejecucion")),
        ("Servidor", meta.get("servidor")),
        ("Duración (seg)", resumen.get("tiempo_proceso_seg")),
        ("Archivos procesados", len(meta["archivos_procesados"]) if isinstance(meta.get("archivos_procesados"), list) else None),
    ]:
        if valor is not None:
            metadata_visible.append(f"**{etiqueta}:** {valor}")
    if metadata_visible:
        st.markdown(" · ".join(metadata_visible))

st.markdown("---")
st.subheader("Distribución de riesgo por motor")
if detalle_registros is None:
    _aviso_fuente("pipeline_detalle.json")
else:
    detalle_df = pd.DataFrame(detalle_registros).reindex(
        columns=["motor", "nivel_riesgo", "event_name", "fecha_bucket"]
    )
    detalle_df = detalle_df[detalle_df["nivel_riesgo"].isin(PRIORIDAD_RIESGO)]
    con_evento = (
        detalle_df["motor"].isin(["multi_cuenta", "self_hedging"])
        & detalle_df["event_name"].notna()
        & detalle_df["event_name"].astype(str).str.strip().ne("")
    )
    casos_evento = detalle_df[con_evento].copy()
    casos_evento["_prioridad"] = casos_evento["nivel_riesgo"].map(PRIORIDAD_RIESGO)
    casos_evento = casos_evento.sort_values("_prioridad", ascending=False).drop_duplicates(
        subset=["motor", "event_name", "fecha_bucket"]
    )
    casos = pd.concat(
        [casos_evento[["motor", "nivel_riesgo"]], detalle_df.loc[~con_evento, ["motor", "nivel_riesgo"]]],
        ignore_index=True,
    )
    conteos = casos.groupby(["motor", "nivel_riesgo"]).size().reset_index(name="Casos")
    if conteos.empty:
        st.info("No hay detecciones con niveles de riesgo disponibles.")
    else:
        chart = alt.Chart(conteos).mark_bar().encode(
            x=alt.X("motor:N", title="Motor"),
            y="Casos:Q",
            color=alt.Color("nivel_riesgo:N", sort=list(PRIORIDAD_RIESGO), title="Nivel de riesgo"),
            tooltip=["motor:N", "nivel_riesgo:N", "Casos:Q"],
        )
        st.altair_chart(chart, use_container_width=True)
        st.dataframe(conteos, use_container_width=True)

st.markdown("---")
st.subheader("AML — 2 capas")
if aml is None:
    _aviso_fuente("aml_pipeline.json")
else:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Candidatos Multi", _kpi_value(aml.get("candidatos_ratio_multi"), "—"))
    col2.metric("Candidatos Self", _kpi_value(aml.get("candidatos_ratio_self"), "—"))
    col3.metric("Total candidatos", _kpi_value(aml.get("total_candidatos_ratio"), "—"))
    col4.metric("Confirmados Hybrid", _kpi_value(aml.get("confirmados_hybrid"), "—"))

st.markdown("---")
st.subheader("Top Usuarios")
if usuarios_df is None:
    _aviso_fuente("pipeline_global.json")
elif usuarios_df.empty:
    st.info("El pipeline no incluye usuarios identificados.")
else:
    st.dataframe(usuarios_df.head(10), use_container_width=True)

st.markdown("---")
st.subheader("Top Eventos")
if detalle_registros is None:
    _aviso_fuente("pipeline_detalle.json")
else:
    eventos_df = _eventos_riesgo(detalle_registros)
    if eventos_df.empty:
        st.info("El pipeline no incluye detecciones con evento.")
    else:
        st.dataframe(eventos_df.head(10), use_container_width=True)

st.markdown("---")
st.subheader("Histórico")
if historico_df is None:
    _aviso_fuente("historico_riesgo_multicuenta.json")
elif historico_df.empty:
    st.info("El histórico no contiene ejecuciones.")
else:
    if {"fecha_ejecucion", "ratio_sospecha_global"}.issubset(historico_df.columns):
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
    else:
        st.info("El histórico no contiene fecha_ejecucion y ratio_sospecha_global para graficar.")
    st.dataframe(historico_df, use_container_width=True)

st.markdown("---")
_panel_usuario(usuarios_df, detalle_registros)

