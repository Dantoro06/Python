"""
Dashboard de Riesgo – Motor Hidding Bonus / Self-Hedging
Módulo para construir reportes JSON y aplicación Streamlit interactiva.
"""

import json
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st
import altair as alt

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPO_ROOT / "src"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from motor.motor_hidding_bonus import (  # pylint: disable=wrong-import-position
    _contar_niveles,
    actualizar_historico_riesgo,
    ejecutar_motor_completo,
)

UTILS_DIR = Path(__file__).resolve().parent
UTILS_DIR.mkdir(exist_ok=True)

HISTORICO_PATH = UTILS_DIR / "historico_riesgo_hiddingbonus.json"
REPORTE_ACTUAL_PATH = UTILS_DIR / "reporte_riesgo_hiddingbonus.json"


def _contar_niveles(df: Optional[pd.DataFrame], col_nivel: str) -> dict:
    """Cuenta niveles de riesgo (ALTO, MEDIO, BAJO) en un DataFrame."""
    conteo = {"ALTO": 0, "MEDIO": 0, "BAJO": 0}
    if df is None or df.empty or col_nivel not in df.columns:
        return conteo
    vc = df[col_nivel].value_counts()
    for k in ["ALTO", "MEDIO", "BAJO"]:
        if k in vc.index:
            conteo[k] = int(vc[k])
    return conteo


def actualizar_historico_riesgo(
    reporte_riesgo: dict,
    ruta_historico: Path = HISTORICO_PATH,
):
    """Actualiza el archivo histórico con datos del nuevo reporte."""
    meta = reporte_riesgo.get("metadata", {})
    resumen = reporte_riesgo.get("resumen_ejecucion", {})
    est = reporte_riesgo.get("estadisticas_riesgo", {})
    fecha_iso = meta.get("fecha_ejecucion", datetime.now().isoformat(timespec="seconds"))
    fecha_dia = fecha_iso[:10]
    total_tx = resumen.get("total_transacciones", 0)
    ratio = resumen.get("ratio_sospecha_global", 0.0)
    multi = est.get("multiusuario", {}) or {}
    selfh = est.get("self_hedging", {}) or {}
    casos_multi = multi.get("casos_totales", 0) or 0
    casos_self = selfh.get("casos_totales", 0) or 0
    total_casos = casos_multi + casos_self
    
    entry = {
        "id_ejecucion": meta.get("id_ejecucion") or f"EXEC-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "fecha_ejecucion": fecha_dia,
        "transacciones_totales": int(total_tx),
        "total_casos_detectados": int(total_casos),
        "ratio_sospecha_global": float(ratio),
        "casos_multiusuario": int(casos_multi),
        "casos_self_hedging": int(casos_self),
    }
    
    if ruta_historico.exists():
        try:
            with ruta_historico.open("r", encoding="utf-8-sig") as f:
                historico = json.load(f)
        except Exception:
            historico = {"ejecuciones": []}
    else:
        historico = {"ejecuciones": []}

    historico.setdefault("ejecuciones", []).append(entry)
    ruta_historico.parent.mkdir(parents=True, exist_ok=True)
    with ruta_historico.open("w", encoding="utf-8-sig") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def construir_reporte_riesgo_dict(
    df_base: pd.DataFrame,
    df_multi: Optional[pd.DataFrame] = None,
    df_self: Optional[pd.DataFrame] = None,
    archivos_entrada: Optional[list] = None,
    total_apuestas_original: Optional[int] = None,
    tolerancia_cobertura: Optional[float] = None,
    min_total_apostado: Optional[float] = None,
    max_apuestas_por_seleccion: Optional[int] = None,
    tiempo_proceso_seg: Optional[float] = None,
) -> dict:
    """Construye un diccionario con el reporte completo de riesgo."""
    df_multi = df_multi if df_multi is not None else pd.DataFrame()
    df_self = df_self if df_self is not None else pd.DataFrame()
    archivos_entrada = archivos_entrada or []

    total_base = len(df_base) if df_base is not None else 0
    total_transacciones = int(total_apuestas_original) if total_apuestas_original is not None else int(total_base)

    usuarios_analizados = 0
    eventos_analizados = 0
    if df_base is not None and not df_base.empty:
        if "user_id" in df_base.columns:
            usuarios_analizados = int(df_base["user_id"].nunique())
        if "event_name" in df_base.columns:
            eventos_analizados = int(df_base["event_name"].nunique())

    casos_multi = len(df_multi) if not df_multi.empty else 0
    casos_self = len(df_self) if not df_self.empty else 0
    casos_sospechosos_totales = casos_multi + casos_self

    if total_transacciones > 0:
        ratio_sospecha_global = casos_sospechosos_totales / total_transacciones
    else:
        ratio_sospecha_global = 0.0

    niveles_multi = _contar_niveles(df_multi, "nivel_riesgo_multi")
    niveles_self = _contar_niveles(df_self, "nivel_riesgo_self")

    usuarios_stats: dict[str, dict] = {}

    if not df_multi.empty and "usuarios_implicados" in df_multi.columns:
        for _, row in df_multi.iterrows():
            ev_name = row.get("event_name", "")
            usuarios_str = str(row["usuarios_implicados"])
            usuarios = [u.strip() for u in usuarios_str.split("|") if u.strip()]
            for u in usuarios:
                if u not in usuarios_stats:
                    usuarios_stats[u] = {"casos_multi": 0, "casos_self": 0, "eventos": set()}
                usuarios_stats[u]["casos_multi"] += 1
                if ev_name:
                    usuarios_stats[u]["eventos"].add(ev_name)

    if not df_self.empty and "usuarios_implicados" in df_self.columns:
        for _, row in df_self.iterrows():
            ev_name = row.get("event_name", "")
            u = str(row["usuarios_implicados"])
            if u not in usuarios_stats:
                usuarios_stats[u] = {"casos_multi": 0, "casos_self": 0, "eventos": set()}
            usuarios_stats[u]["casos_self"] += 1
            if ev_name:
                usuarios_stats[u]["eventos"].add(ev_name)

    top_usuarios_riesgo = []
    for u, data_u in usuarios_stats.items():
        total_casos = data_u["casos_multi"] + data_u["casos_self"]
        tipos = []
        if data_u["casos_multi"] > 0:
            tipos.append("multiusuario")
        if data_u["casos_self"] > 0:
            tipos.append("self_hedging")
        top_usuarios_riesgo.append({
            "usuario_id": u,
            "casos_total": total_casos,
            "casos_multiusuario": data_u["casos_multi"],
            "casos_self_hedging": data_u["casos_self"],
            "eventos_involucrados": len(data_u["eventos"]),
            "tipos_riesgo": tipos,
        })

    top_usuarios_riesgo.sort(key=lambda x: x["casos_total"], reverse=True)
    top_usuarios_riesgo = top_usuarios_riesgo[:20]

    eventos_stats: dict[str, dict] = {}

    def _agg_eventos(df_local: pd.DataFrame, fuente: str, col_nivel: str):
        """Agrega información de eventos por fuente de riesgo."""
        if df_local.empty:
            return
        for _, row in df_local.iterrows():
            ev_name = row.get("event_name", "")
            if not ev_name:
                continue
            usuarios_str = str(row.get("usuarios_implicados", ""))
            usuarios = [u.strip() for u in usuarios_str.split("|") if u.strip()]
            if not usuarios:
                usuarios = [usuarios_str.strip()] if usuarios_str.strip() else []

            nivel = str(row.get(col_nivel, "")).upper()

            if ev_name not in eventos_stats:
                eventos_stats[ev_name] = {"usuarios": set(), "fuentes": set(), "niveles": set()}
            eventos_stats[ev_name]["fuentes"].add(fuente)
            for u in usuarios:
                if u:
                    eventos_stats[ev_name]["usuarios"].add(u)
            if nivel:
                eventos_stats[ev_name]["niveles"].add(nivel)

    _agg_eventos(df_multi, "multiusuario", "nivel_riesgo_multi")
    _agg_eventos(df_self, "self_hedging", "nivel_riesgo_self")

    def _max_riesgo(niveles: set) -> str:
        """Retorna el nivel de riesgo máximo de un conjunto."""
        if not niveles:
            return ""
        prioridad = {"ALTO": 3, "MEDIO": 2, "BAJO": 1}
        mejor_nivel = None
        mejor_score = 0
        for n in niveles:
            score = prioridad.get(n.upper(), 0)
            if score > mejor_score:
                mejor_score = score
                mejor_nivel = n.upper()
        return mejor_nivel or ""

    top_eventos_sospechosos = []
    for ev_name, data_ev in eventos_stats.items():
        fuentes = list(sorted(data_ev["fuentes"]))
        riesgo_max = _max_riesgo(data_ev["niveles"])
        top_eventos_sospechosos.append({
            "evento_id": ev_name,
            "usuarios_involucrados": len(data_ev["usuarios"]),
            "fuentes": fuentes,
            "riesgo_maximo": riesgo_max,
        })

    top_eventos_sospechosos.sort(key=lambda x: (x["riesgo_maximo"] != "ALTO", -x["usuarios_involucrados"]))
    top_eventos_sospechosos = top_eventos_sospechosos[:20]

    parametros_motor = {
        "tolerancia_cobertura": tolerancia_cobertura,
        "min_total_apostado": min_total_apostado,
        "max_apuestas_por_seleccion": max_apuestas_por_seleccion,
    }

    return {
        "metadata": {
            "nombre_motor": "HiddingBonusRiskEngine",
            "version": "1.0.0",
            "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
            "servidor": socket.gethostname(),
            "archivos_procesados": list(archivos_entrada),
        },
        "resumen_ejecucion": {
            "total_transacciones": total_transacciones,
            "usuarios_analizados": usuarios_analizados,
            "eventos_analizados": eventos_analizados,
            "tiempo_proceso_seg": round(tiempo_proceso_seg, 2) if tiempo_proceso_seg is not None else None,
            "ratio_sospecha_global": round(ratio_sospecha_global, 6),
        },
        "estadisticas_riesgo": {
            "multiusuario": {"casos_totales": casos_multi, "por_nivel": niveles_multi},
            "self_hedging": {"casos_totales": casos_self, "por_nivel": niveles_self},
        },
        "top_usuarios_riesgo": top_usuarios_riesgo,
        "top_eventos_sospechosos": top_eventos_sospechosos,
        "parametros_motor": parametros_motor,
    }


def generar_reporte_json(
    df_base: pd.DataFrame,
    df_multi: Optional[pd.DataFrame] = None,
    df_self: Optional[pd.DataFrame] = None,
    archivos_entrada: Optional[list] = None,
    total_apuestas_original: Optional[int] = None,
    tolerancia_cobertura: Optional[float] = None,
    min_total_apostado: Optional[float] = None,
    max_apuestas_por_seleccion: Optional[int] = None,
    tiempo_proceso_seg: Optional[float] = None,
    nombre_archivo: Path = REPORTE_ACTUAL_PATH,
) -> dict:
    """Genera y guarda un reporte JSON de riesgo, actualiza histórico."""
    reporte_riesgo = construir_reporte_riesgo_dict(
        df_base=df_base,
        df_multi=df_multi,
        df_self=df_self,
        archivos_entrada=archivos_entrada,
        total_apuestas_original=total_apuestas_original,
        tolerancia_cobertura=tolerancia_cobertura,
        min_total_apostado=min_total_apostado,
        max_apuestas_por_seleccion=max_apuestas_por_seleccion,
        tiempo_proceso_seg=tiempo_proceso_seg,
    )

    nombre_archivo = Path(nombre_archivo)
    nombre_archivo.parent.mkdir(parents=True, exist_ok=True)

    with nombre_archivo.open("w", encoding="utf-8-sig") as f:
        json.dump(reporte_riesgo, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"📁 Reporte de riesgo guardado en: {nombre_archivo}")
    print("   → Este archivo se puede usar directamente en Gemini AI Studio")
    print("=" * 60 + "\n")

    try:
        actualizar_historico_riesgo(reporte_riesgo)
    except Exception as e:
        print(f"[WARN] No se pudo actualizar el histórico de riesgo: {e}")

    return reporte_riesgo


def cargar_historico(path: Path | str = HISTORICO_PATH) -> pd.DataFrame:
    """Carga el histórico de ejecuciones desde JSON y retorna un DataFrame."""
    path = Path(path)

    if not path.exists():
        return pd.DataFrame()

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return pd.DataFrame()

    ejecuciones = data.get("ejecuciones", [])
    if not ejecuciones:
        return pd.DataFrame()

    df = pd.DataFrame(ejecuciones)

    if "fecha_ejecucion" in df.columns:
        df["fecha_ejecucion"] = pd.to_datetime(df["fecha_ejecucion"], errors="coerce")

    for col in ["transacciones_totales", "total_casos_detectados", "casos_multiusuario", "casos_self_hedging"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    if "ratio_sospecha_global" in df.columns:
        df["ratio_sospecha_global"] = pd.to_numeric(df["ratio_sospecha_global"], errors="coerce").fillna(0.0)

    df = df.sort_values("fecha_ejecucion")
    return df


def cargar_reporte_actual(path: Path | str = REPORTE_ACTUAL_PATH) -> dict:
    """Carga el reporte actual (última ejecución) desde JSON."""
    path = Path(path)

    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def formatear_pct(x: float) -> str:
    """Formatea un número decimal como porcentaje."""
    return f"{x * 100:.2f}%"


def main():
    """Función principal de la aplicación Streamlit."""
    st.set_page_config(page_title="Nueve11 Risk Monitor", page_icon="📊", layout="wide")

    st.title("Nueve11 Risk Monitor")
    st.caption("Motor de riesgo Hidding Bonus / Self-Hedging — Panel histórico y detalle")

    df_hist = cargar_historico()

    if df_hist.empty:
        st.error(f"No se encontró información histórica en '{HISTORICO_PATH}'. Ejecuta el motor al menos una vez para generar el histórico.")
        st.stop()

    # === FILTROS ===
    min_date = df_hist["fecha_ejecucion"].min().date()
    max_date = df_hist["fecha_ejecucion"].max().date()

    st.sidebar.header("Filtros")
    fecha_desde, fecha_hasta = st.sidebar.date_input(
        "Rango de fechas (ejecuciones históricas)",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    if isinstance(fecha_desde, datetime):
        fecha_desde = fecha_desde.date()
    if isinstance(fecha_hasta, datetime):
        fecha_hasta = fecha_hasta.date()

    if fecha_desde > fecha_hasta:
        st.sidebar.error("La fecha 'desde' no puede ser mayor que la fecha 'hasta'.")
        st.stop()

    st.sidebar.markdown("---")
    st.sidebar.subheader("Umbrales de alerta")

    ratio_yellow = st.sidebar.number_input("Umbral ratio sospecha - Alerta amarilla (%)", min_value=0.0, max_value=100.0, value=5.0, step=0.1)
    ratio_red = st.sidebar.number_input("Umbral ratio sospecha - Alerta roja (%)", min_value=0.0, max_value=100.0, value=10.0, step=0.1)
    umbral_usuarios_sospechosos = st.sidebar.number_input("Umbral usuarios sospechosos (última ejecución)", min_value=0, value=50, step=1)
    umbral_eventos_criticos = st.sidebar.number_input("Umbral eventos bajo lupa (última ejecución)", min_value=0, value=10, step=1)

    # === FILTRADO ===
    df_scope = df_hist[(df_hist["fecha_ejecucion"].dt.date >= fecha_desde) & (df_hist["fecha_ejecucion"].dt.date <= fecha_hasta)].copy()

    if df_scope.empty:
        st.warning("No hay ejecuciones dentro del rango de fechas seleccionado. Ajusta el filtro en la barra lateral.")
        st.stop()

    # === KPIs ===
    num_ejecuciones = len(df_scope)
    transacciones_acum = int(df_scope["transacciones_totales"].sum())
    casos_acum = int(df_scope["total_casos_detectados"].sum())
    ratio_prom = df_scope["ratio_sospecha_global"].mean() if num_ejecuciones > 0 else 0.0

    ultima = df_hist.iloc[-1]
    ratio_ultima = float(ultima.get("ratio_sospecha_global", 0.0))
    ratio_ultima_pct = ratio_ultima * 100.0

    diff_vs_prom = ((ratio_ultima - ratio_prom) / ratio_prom * 100.0) if ratio_prom > 0 else 0.0

    # === DASHBOARD ===
    st.subheader("📈 Dashboard histórico")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="Transacciones acumuladas", value=f"{transacciones_acum:,.0f}".replace(",", "."))
    with col2:
        st.metric(label="Casos sospechosos acumulados", value=f"{casos_acum:,.0f}".replace(",", "."))
    with col3:
        st.metric(label="Promedio histórico ratio sospecha", value=formatear_pct(ratio_prom))
    with col4:
        delta_str = f"{diff_vs_prom:+.1f} pp"
        st.metric(label="Última ejecución vs promedio", value=formatear_pct(ratio_ultima), delta=delta_str)

    st.markdown("")

    if ratio_ultima_pct >= ratio_red:
        st.error(f"⚠️ Ratio de sospecha MUY ALTO en la última ejecución ({ratio_ultima_pct:.2f}%). Umbral roja: {ratio_red:.2f}%.")
    elif ratio_ultima_pct >= ratio_yellow:
        st.warning(f"🔶 Ratio de sospecha elevado en la última ejecución ({ratio_ultima_pct:.2f}%). Umbral amarilla: {ratio_yellow:.2f}%.")
    else:
        st.success(f"✅ Ratio de sospecha dentro de rangos esperados ({ratio_ultima_pct:.2f}%). Umbral amarilla: {ratio_yellow:.2f}% · Umbral roja: {ratio_red:.2f}%.")

    st.markdown("---")

    # === GRÁFICOS ===
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown("#### Tendencia del ratio de sospecha (%)")
        df_chart = df_scope[["fecha_ejecucion", "ratio_sospecha_global"]].copy()
        df_chart = df_chart.set_index("fecha_ejecucion")
        df_chart["Ratio sospecha (%)"] = df_chart["ratio_sospecha_global"] * 100
        st.line_chart(df_chart["Ratio sospecha (%)"])

    with col_right:
        st.markdown("#### Top 5 días críticos (por ratio)")
        df_top = df_scope.copy()
        df_top["Ratio (%)"] = df_top["ratio_sospecha_global"] * 100
        df_top = df_top.sort_values("ratio_sospecha_global", ascending=False).head(5)

        tabla_top = df_top[["fecha_ejecucion", "Ratio (%)", "total_casos_detectados", "transacciones_totales"]].copy()
        tabla_top["fecha_ejecucion"] = tabla_top["fecha_ejecucion"].dt.strftime("%d/%m/%Y")
        tabla_top["Ratio (%)"] = tabla_top["Ratio (%)"].map(lambda x: f"{x:.2f}%")
        tabla_top.rename(columns={
            "fecha_ejecucion": "Fecha",
            "Ratio (%)": "Ratio sospecha",
            "total_casos_detectados": "Casos",
            "transacciones_totales": "Transacciones",
        }, inplace=True)

        st.table(tabla_top)

    st.markdown("---")

    # === DETALLE ÚLTIMA EJECUCIÓN ===
    st.subheader("🔍 Detalle de la última ejecución")

    reporte_actual = cargar_reporte_actual()

    top_users = []
    top_events = []
    total_tx_last = total_casos_last = 0
    casos_multi_last = casos_self_last = 0
    ratio_last = 0.0

    if not reporte_actual:
        st.info(f"No se encontró '{REPORTE_ACTUAL_PATH}'. Solo se muestran datos históricos agregados.")
    else:
        meta = reporte_actual.get("metadata", {})
        resumen = reporte_actual.get("resumen_ejecucion", {})
        est = reporte_actual.get("estadisticas_riesgo", {})
        top_users = reporte_actual.get("top_usuarios_riesgo", [])
        top_events = reporte_actual.get("top_eventos_sospechosos", [])

        fecha_rep = meta.get("fecha_ejecucion", "")
        archivos_proc = meta.get("archivos_procesados", [])

        st.caption(f"Ejecución: {fecha_rep} — Archivos procesados: {', '.join(archivos_proc)}")

        col_a, col_b, col_c, col_d, col_e = st.columns(5)

        total_tx_last = resumen.get("total_transacciones", 0)
        total_casos_last = (est.get("multiusuario", {}) or {}).get("casos_totales", 0) + (est.get("self_hedging", {}) or {}).get("casos_totales", 0)
        ratio_last = resumen.get("ratio_sospecha_global", 0.0)
        casos_multi_last = (est.get("multiusuario", {}) or {}).get("casos_totales", 0)
        casos_self_last = (est.get("self_hedging", {}) or {}).get("casos_totales", 0)

        with col_a:
            st.metric(label="Transacciones analizadas (última ejecución)", value=f"{total_tx_last:,.0f}".replace(",", "."))
        with col_b:
            st.metric(label="Casos sospechosos (última ejecución)", value=f"{total_casos_last:,.0f}".replace(",", "."))
        with col_c:
            st.metric(label="Ratio sospecha (última ejecución)", value=formatear_pct(ratio_last))
        with col_d:
            st.metric(label="Casos multiusuario", value=f"{casos_multi_last:,.0f}".replace(",", "."))
        with col_e:
            st.metric(label="Casos self-hedging", value=f"{casos_self_last:,.0f}".replace(",", "."))

        st.markdown("")

        col_l, col_r = st.columns(2)

        with col_l:
            st.markdown("##### Casos por tipo de riesgo (última ejecución)")
            df_tipos = pd.DataFrame({"Tipo de riesgo": ["Multiusuario", "Self-hedging"], "Casos": [casos_multi_last, casos_self_last]})
            chart_tipos = alt.Chart(df_tipos).mark_bar().encode(x=alt.X("Tipo de riesgo:N", sort=None), y="Casos:Q", tooltip=["Tipo de riesgo", "Casos"])
            st.altair_chart(chart_tipos, use_container_width=True)

        with col_r:
            st.markdown("##### Distribución por nivel de riesgo (combinado)")
            niveles_total = {"ALTO": 0, "MEDIO": 0, "BAJO": 0}
            multi_por_nivel = (est.get("multiusuario", {}) or {}).get("por_nivel", {})
            self_por_nivel = (est.get("self_hedging", {}) or {}).get("por_nivel", {})
            for niv in niveles_total.keys():
                niveles_total[niv] = int(multi_por_nivel.get(niv, 0)) + int(self_por_nivel.get(niv, 0))

            df_niveles = pd.DataFrame({"Nivel": list(niveles_total.keys()), "Casos": list(niveles_total.values())})
            chart_niveles = alt.Chart(df_niveles).mark_bar().encode(x=alt.X("Nivel:N", sort=["ALTO", "MEDIO", "BAJO"]), y="Casos:Q", tooltip=["Nivel", "Casos"])
            st.altair_chart(chart_niveles, use_container_width=True)

        st.markdown("")

        num_usuarios_top = len(top_users) if isinstance(top_users, list) else 0
        num_eventos_top = len(top_events) if isinstance(top_events, list) else 0

        if num_usuarios_top >= umbral_usuarios_sospechosos or num_eventos_top >= umbral_eventos_criticos:
            st.warning(f"⚠️ Actividad sospechosa relevante · Usuarios: {num_usuarios_top} (umbral {umbral_usuarios_sospechosos}) · Eventos: {num_eventos_top} (umbral {umbral_eventos_criticos}).")
        else:
            st.info(f"ℹ️ TOP dentro de umbrales · Usuarios: {num_usuarios_top}/{umbral_usuarios_sospechosos} · Eventos: {num_eventos_top}/{umbral_eventos_criticos}.")

        st.markdown("---")

        col_u, col_ev = st.columns(2)

        with col_u:
            st.markdown("#### 🧑‍💻 Top usuarios sospechosos (última ejecución)")
            if not top_users:
                st.write("No hay información de usuarios en el reporte.")
            else:
                df_u = pd.DataFrame(top_users)
                if "casos_total" in df_u.columns:
                    df_u = df_u.sort_values("casos_total", ascending=False)
                st.dataframe(df_u, use_container_width=True, height=300)

        with col_ev:
            st.markdown("#### 🎯 Top eventos bajo lupa (última ejecución)")
            if not top_events:
                st.write("No hay información de eventos en el reporte.")
            else:
                df_e = pd.DataFrame(top_events)
                if "usuarios_involucrados" in df_e.columns:
                    df_e = df_e.sort_values("usuarios_involucrados", ascending=False)
                st.dataframe(df_e, use_container_width=True, height=300)

    # === VISUALIZACIONES AVANZADAS ===
    st.markdown("---")
    st.subheader("📊 Visualizaciones avanzadas")

    if {"casos_multiusuario", "casos_self_hedging"}.issubset(df_scope.columns):
        st.markdown("##### 🔥 Heatmap de casos por tipo y fecha")
        df_heat = df_scope[["fecha_ejecucion", "casos_multiusuario", "casos_self_hedging"]].copy()
        df_heat["fecha"] = df_heat["fecha_ejecucion"].dt.date.astype(str)
        df_heat = df_heat.melt(id_vars="fecha", value_vars=["casos_multiusuario", "casos_self_hedging"], var_name="tipo_riesgo", value_name="casos")
        df_heat["tipo_riesgo"] = df_heat["tipo_riesgo"].replace({"casos_multiusuario": "Multiusuario", "casos_self_hedging": "Self-hedging"})

        chart_heat = alt.Chart(df_heat).mark_rect().encode(
            x=alt.X("fecha:N", title="Fecha", sort="ascending"),
            y=alt.Y("tipo_riesgo:N", title="Tipo de riesgo"),
            color=alt.Color("casos:Q", title="Casos"),
            tooltip=["fecha", "tipo_riesgo", "casos"],
        ).properties(height=200)
        st.altair_chart(chart_heat, use_container_width=True)

    if top_users:
        st.markdown("##### 📦 Distribución de casos por usuario (última ejecución)")
        df_u = pd.DataFrame(top_users)
        if "casos_total" in df_u.columns:
            chart_hist = alt.Chart(df_u).mark_bar().encode(
                x=alt.X("casos_total:Q", bin=alt.Bin(maxbins=20), title="Casos totales por usuario"),
                y=alt.Y("count():Q", title="Número de usuarios"),
                tooltip=["count()"],
            )
            st.altair_chart(chart_hist, use_container_width=True)

    if total_tx_last > 0:
        st.markdown("##### 🔁 Flujo de detección (última ejecución)")
        df_funnel = pd.DataFrame({
            "Etapa": ["Transacciones analizadas", "Casos multiusuario", "Casos self-hedging", "Casos sospechosos totales"],
            "Valor": [int(total_tx_last), int(casos_multi_last), int(casos_self_last), int(total_casos_last)],
        })
        chart_funnel = alt.Chart(df_funnel).mark_bar().encode(x=alt.X("Etapa:N", sort=None), y="Valor:Q", tooltip=["Etapa", "Valor"])
        st.altair_chart(chart_funnel, use_container_width=True)

    st.markdown("---")
    st.markdown("##### 📋 Detalle de ejecuciones históricas")

    df_tabla = df_scope.copy()
    df_tabla["Fecha"] = df_tabla["fecha_ejecucion"].dt.strftime("%d/%m/%Y")
    df_tabla["Ratio sospecha (%)"] = df_tabla["ratio_sospecha_global"].map(lambda x: f"{x*100:.2f}%")

    cols_show = ["Fecha", "id_ejecucion", "transacciones_totales", "total_casos_detectados", "casos_multiusuario", "casos_self_hedging", "Ratio sospecha (%)"]

    st.dataframe(df_tabla[cols_show], use_container_width=True)

    # === DESCARGAS ===
    st.markdown("##### 📁 Descarga de datos")

    col_d1, col_d2, col_d3 = st.columns(3)

    with col_d1:
        csv_hist = df_tabla[cols_show].to_csv(index=False).encode("utf-8-sig")
        st.download_button(label="⬇️ Histórico filtrado (CSV)", data=csv_hist, file_name="historico_riesgo_filtrado.csv", mime="text/csv")

    if top_users:
        with col_d2:
            df_top_u = pd.DataFrame(top_users)
            csv_top_u = df_top_u.to_csv(index=False).encode("utf-8-sig")
            st.download_button(label="⬇️ Top usuarios sospechosos (CSV)", data=csv_top_u, file_name="top_usuarios_sospechosos_ultima_ejecucion.csv", mime="text/csv")

    if top_events:
        with col_d3:
            df_top_e = pd.DataFrame(top_events)
            csv_top_e = df_top_e.to_csv(index=False).encode("utf-8-sig")
            st.download_button(label="⬇️ Top eventos bajo lupa (CSV)", data=csv_top_e, file_name="top_eventos_bajo_lupa_ultima_ejecucion.csv", mime="text/csv")


if __name__ == "__main__":
    main()
