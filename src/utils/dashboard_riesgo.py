import os
import json
from datetime import datetime

import pandas as pd
import streamlit as st
import altair as alt

HISTORICO_PATH = "historico_riesgo_hiddingbonus.json"
REPORTE_ACTUAL_PATH = "reporte_riesgo_hiddingbonus.json"


# ---------------------------------------------
# Carga y preparación de datos
# ---------------------------------------------


def cargar_historico(path: str = HISTORICO_PATH) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ejecuciones = data.get("ejecuciones", [])
    if not ejecuciones:
        return pd.DataFrame()

    df = pd.DataFrame(ejecuciones)

    # Parse fecha
    if "fecha_ejecucion" in df.columns:
        df["fecha_ejecucion"] = pd.to_datetime(df["fecha_ejecucion"], errors="coerce")

    # Numeric coercion
    for col in [
        "transacciones_totales",
        "total_casos_detectados",
        "casos_multiusuario",
        "casos_self_hedging",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    if "ratio_sospecha_global" in df.columns:
        df["ratio_sospecha_global"] = pd.to_numeric(
            df["ratio_sospecha_global"], errors="coerce"
        ).fillna(0.0)

    df = df.sort_values("fecha_ejecucion")
    return df


def cargar_reporte_actual(path: str = REPORTE_ACTUAL_PATH) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def formatear_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


# ---------------------------------------------
# App Streamlit
# ---------------------------------------------


st.set_page_config(
    page_title="Nueve11 Risk Monitor",
    page_icon="📊",
    layout="wide",
)

st.title("Nueve11 Risk Monitor")
st.caption("Motor de riesgo Hidding Bonus / Self-Hedging — Panel histórico y detalle")

df_hist = cargar_historico()

if df_hist.empty:
    st.error(
        f"No se encontró información histórica en '{HISTORICO_PATH}'. "
        "Ejecuta el motor al menos una vez para generar el histórico."
    )
    st.stop()

# ---------------------------------------------
# Filtros (sidebar) – rango de fechas + umbrales
# ---------------------------------------------

min_date = df_hist["fecha_ejecucion"].min().date()
max_date = df_hist["fecha_ejecucion"].max().date()

st.sidebar.header("Filtros")

fecha_desde, fecha_hasta = st.sidebar.date_input(
    "Rango de fechas (ejecuciones históricas)",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)

# Normalizar tipos (por si vienen como datetime)
if isinstance(fecha_desde, datetime):
    fecha_desde = fecha_desde.date()
if isinstance(fecha_hasta, datetime):
    fecha_hasta = fecha_hasta.date()

if fecha_desde > fecha_hasta:
    st.sidebar.error("La fecha 'desde' no puede ser mayor que la fecha 'hasta'.")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.subheader("Umbrales de alerta")

ratio_yellow = st.sidebar.number_input(
    "Umbral ratio sospecha - Alerta amarilla (%)",
    min_value=0.0,
    max_value=100.0,
    value=5.0,
    step=0.1,
)
ratio_red = st.sidebar.number_input(
    "Umbral ratio sospecha - Alerta roja (%)",
    min_value=0.0,
    max_value=100.0,
    value=10.0,
    step=0.1,
)
umbral_usuarios_sospechosos = st.sidebar.number_input(
    "Umbral usuarios sospechosos (última ejecución)",
    min_value=0,
    value=50,
    step=1,
)
umbral_eventos_criticos = st.sidebar.number_input(
    "Umbral eventos bajo lupa (última ejecución)",
    min_value=0,
    value=10,
    step=1,
)

# Filtrar el histórico según el rango
df_scope = df_hist[
    (df_hist["fecha_ejecucion"].dt.date >= fecha_desde)
    & (df_hist["fecha_ejecucion"].dt.date <= fecha_hasta)
].copy()

if df_scope.empty:
    st.warning(
        "No hay ejecuciones dentro del rango de fechas seleccionado. "
        "Ajusta el filtro en la barra lateral."
    )
    st.stop()

# KPIs históricos sobre el rango filtrado
num_ejecuciones = len(df_scope)
transacciones_acum = int(df_scope["transacciones_totales"].sum())
casos_acum = int(df_scope["total_casos_detectados"].sum())
ratio_prom = df_scope["ratio_sospecha_global"].mean() if num_ejecuciones > 0 else 0.0

# La última ejecución real del histórico completo (no filtrado)
ultima = df_hist.iloc[-1]
ratio_ultima = float(ultima.get("ratio_sospecha_global", 0.0))
fecha_ultima = ultima.get("fecha_ejecucion")
ratio_ultima_pct = ratio_ultima * 100.0

diff_vs_prom = (
    ((ratio_ultima - ratio_prom) / ratio_prom * 100.0) if ratio_prom > 0 else 0.0
)

# ---------------------------------------------
# Dashboard histórico (parte de arriba)
# ---------------------------------------------

st.subheader("📈 Dashboard histórico")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="Transacciones acumuladas",
        value=f"{transacciones_acum:,.0f}".replace(",", "."),
    )
with col2:
    st.metric(
        label="Casos sospechosos acumulados",
        value=f"{casos_acum:,.0f}".replace(",", "."),
    )
with col3:
    st.metric(
        label="Promedio histórico ratio sospecha",
        value=formatear_pct(ratio_prom),
    )
with col4:
    label_ult = "Última ejecución vs promedio"
    delta_str = f"{diff_vs_prom:+.1f} pp"
    st.metric(
        label=label_ult,
        value=formatear_pct(ratio_ultima),
        delta=delta_str,
    )

# Bloque de alerta según ratio de la última ejecución + umbrales configurables
st.markdown("")

if ratio_ultima_pct >= ratio_red:
    st.error(
        f"⚠️ Ratio de sospecha MUY ALTO en la última ejecución "
        f"({ratio_ultima_pct:.2f}%). Umbral roja: {ratio_red:.2f}%."
    )
elif ratio_ultima_pct >= ratio_yellow:
    st.warning(
        f"🔶 Ratio de sospecha elevado en la última ejecución "
        f"({ratio_ultima_pct:.2f}%). Umbral amarilla: {ratio_yellow:.2f}%."
    )
else:
    st.success(
        f"✅ Ratio de sospecha dentro de rangos esperados "
        f"({ratio_ultima_pct:.2f}%). "
        f"Umbral amarilla: {ratio_yellow:.2f}% · Umbral roja: {ratio_red:.2f}%."
    )

st.markdown("---")

# ---------------------------------------------
# Tendencia + Top 5 días críticos
# ---------------------------------------------

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

    tabla_top = df_top[
        ["fecha_ejecucion", "Ratio (%)", "total_casos_detectados", "transacciones_totales"]
    ].copy()
    tabla_top["fecha_ejecucion"] = tabla_top["fecha_ejecucion"].dt.strftime("%d/%m/%Y")
    tabla_top["Ratio (%)"] = tabla_top["Ratio (%)"].map(lambda x: f"{x:.2f}%")
    tabla_top.rename(
        columns={
            "fecha_ejecucion": "Fecha",
            "Ratio (%)": "Ratio sospecha",
            "total_casos_detectados": "Casos",
            "transacciones_totales": "Transacciones",
        },
        inplace=True,
    )

    st.table(tabla_top)

st.markdown("---")

# ---------------------------------------------
# Detalle de la última ejecución
# ---------------------------------------------

st.subheader("🔍 Detalle de la última ejecución")

reporte_actual = cargar_reporte_actual()

top_users = []
top_events = []
total_tx_last = total_casos_last = 0
casos_multi_last = casos_self_last = 0
ratio_last = 0.0

if not reporte_actual:
    st.info(
        f"No se encontró '{REPORTE_ACTUAL_PATH}'. "
        "Solo se muestran datos históricos agregados."
    )
else:
    meta = reporte_actual.get("metadata", {})
    resumen = reporte_actual.get("resumen_ejecucion", {})
    est = reporte_actual.get("estadisticas_riesgo", {})
    top_users = reporte_actual.get("top_usuarios_riesgo", [])
    top_events = reporte_actual.get("top_eventos_sospechosos", [])

    fecha_rep = meta.get("fecha_ejecucion", "")
    archivos_proc = meta.get("archivos_procesados", [])

    st.caption(
        f"Ejecución: {fecha_rep} — Archivos procesados: "
        + ", ".join(archivos_proc)
    )

    col_a, col_b, col_c, col_d, col_e = st.columns(5)

    total_tx_last = resumen.get("total_transacciones", 0)
    total_casos_last = (
        (est.get("multiusuario", {}) or {}).get("casos_totales", 0)
        + (est.get("self_hedging", {}) or {}).get("casos_totales", 0)
    )
    ratio_last = resumen.get("ratio_sospecha_global", 0.0)

    casos_multi_last = (est.get("multiusuario", {}) or {}).get("casos_totales", 0)
    casos_self_last = (est.get("self_hedging", {}) or {}).get("casos_totales", 0)

    with col_a:
        st.metric(
            label="Transacciones analizadas (última ejecución)",
            value=f"{total_tx_last:,.0f}".replace(",", "."),
        )
    with col_b:
        st.metric(
            label="Casos sospechosos (última ejecución)",
            value=f"{total_casos_last:,.0f}".replace(",", "."),
        )
    with col_c:
        st.metric(
            label="Ratio sospecha (última ejecución)",
            value=formatear_pct(ratio_last),
        )
    with col_d:
        st.metric(
            label="Casos multiusuario",
            value=f"{casos_multi_last:,.0f}".replace(",", "."),
        )
    with col_e:
        st.metric(
            label="Casos self-hedging",
            value=f"{casos_self_last:,.0f}".replace(",", "."),
        )

    st.markdown("")

    col_l, col_r = st.columns(2)

    # Casos por tipo (multi vs self)
    with col_l:
        st.markdown("##### Casos por tipo de riesgo (última ejecución)")
        df_tipos = pd.DataFrame(
            {
                "Tipo de riesgo": ["Multiusuario", "Self-hedging"],
                "Casos": [casos_multi_last, casos_self_last],
            }
        )
        chart_tipos = (
            alt.Chart(df_tipos)
            .mark_bar()
            .encode(
                x=alt.X("Tipo de riesgo:N", sort=None),
                y="Casos:Q",
                tooltip=["Tipo de riesgo", "Casos"],
            )
        )
        st.altair_chart(chart_tipos, use_container_width=True)

    # Distribución por nivel si existe
    with col_r:
        st.markdown("##### Distribución por nivel de riesgo (combinado)")

        niveles_total = {"ALTO": 0, "MEDIO": 0, "BAJO": 0}

        multi_por_nivel = (est.get("multiusuario", {}) or {}).get("por_nivel", {})
        self_por_nivel = (est.get("self_hedging", {}) or {}).get("por_nivel", {})

        for niv in niveles_total.keys():
            niveles_total[niv] = int(multi_por_nivel.get(niv, 0)) + int(
                self_por_nivel.get(niv, 0)
            )

        df_niveles = pd.DataFrame(
            {
                "Nivel": list(niveles_total.keys()),
                "Casos": list(niveles_total.values()),
            }
        )
        chart_niveles = (
            alt.Chart(df_niveles)
            .mark_bar()
            .encode(
                x=alt.X("Nivel:N", sort=["ALTO", "MEDIO", "BAJO"]),
                y="Casos:Q",
                tooltip=["Nivel", "Casos"],
            )
        )
        st.altair_chart(chart_niveles, use_container_width=True)

    # Alertas adicionales basadas en umbrales de usuarios y eventos
    st.markdown("")

    num_usuarios_top = len(top_users) if isinstance(top_users, list) else 0
    num_eventos_top = len(top_events) if isinstance(top_events, list) else 0

    if num_usuarios_top >= umbral_usuarios_sospechosos or num_eventos_top >= umbral_eventos_criticos:
        st.warning(
            f"⚠️ Actividad sospechosa relevante en la última ejecución · "
            f"Usuarios en TOP: {num_usuarios_top} (umbral {umbral_usuarios_sospechosos}) · "
            f"Eventos en TOP: {num_eventos_top} (umbral {umbral_eventos_criticos})."
        )
    else:
        st.info(
            f"ℹ️ TOP de usuarios/eventos dentro de umbrales configurados · "
            f"Usuarios: {num_usuarios_top}/{umbral_usuarios_sospechosos} · "
            f"Eventos: {num_eventos_top}/{umbral_eventos_criticos}."
        )

    st.markdown("---")

    # Tablas de detalle: top usuarios y top eventos
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

# ---------------------------------------------
# Visualizaciones avanzadas adicionales
# ---------------------------------------------

st.markdown("---")
st.subheader("📊 Visualizaciones avanzadas de riesgo")

# 1) Heatmap histórico por tipo de riesgo (multi vs self)
if {"casos_multiusuario", "casos_self_hedging"}.issubset(df_scope.columns):
    st.markdown("##### 🔥 Heatmap de casos por tipo de riesgo y fecha")

    df_heat = df_scope[["fecha_ejecucion", "casos_multiusuario", "casos_self_hedging"]].copy()
    df_heat["fecha"] = df_heat["fecha_ejecucion"].dt.date.astype(str)
    df_heat = df_heat.melt(
        id_vars="fecha",
        value_vars=["casos_multiusuario", "casos_self_hedging"],
        var_name="tipo_riesgo",
        value_name="casos",
    )
    df_heat["tipo_riesgo"] = df_heat["tipo_riesgo"].replace(
        {
            "casos_multiusuario": "Multiusuario",
            "casos_self_hedging": "Self-hedging",
        }
    )

    chart_heat = (
        alt.Chart(df_heat)
        .mark_rect()
        .encode(
            x=alt.X("fecha:N", title="Fecha", sort="ascending"),
            y=alt.Y("tipo_riesgo:N", title="Tipo de riesgo"),
            color=alt.Color("casos:Q", title="Casos"),
            tooltip=["fecha", "tipo_riesgo", "casos"],
        )
    ).properties(height=200)
    st.altair_chart(chart_heat, use_container_width=True)

# 2) Distribución de casos por usuario sospechoso
if top_users:
    st.markdown("##### 📦 Distribución de casos por usuario sospechoso (última ejecución)")

    df_u = pd.DataFrame(top_users)
    if "casos_total" in df_u.columns:
        chart_hist = (
            alt.Chart(df_u)
            .mark_bar()
            .encode(
                x=alt.X("casos_total:Q", bin=alt.Bin(maxbins=20), title="Casos totales por usuario"),
                y=alt.Y("count():Q", title="Número de usuarios"),
                tooltip=["count()"],
            )
        )
        st.altair_chart(chart_hist, use_container_width=True)
    else:
        st.write("No se encontró el campo 'casos_total' para construir la distribución.")

# 3) Flujo de detección (funnel simple)
if total_tx_last > 0:
    st.markdown("##### 🔁 Flujo de detección de casos (última ejecución)")

    df_funnel = pd.DataFrame(
        {
            "Etapa": [
                "Transacciones analizadas",
                "Casos multiusuario",
                "Casos self-hedging",
                "Casos sospechosos totales",
            ],
            "Valor": [
                int(total_tx_last),
                int(casos_multi_last),
                int(casos_self_last),
                int(total_casos_last),
            ],
        }
    )

    chart_funnel = (
        alt.Chart(df_funnel)
        .mark_bar()
        .encode(
            x=alt.X("Etapa:N", sort=None),
            y=alt.Y("Valor:Q"),
            tooltip=["Etapa", "Valor"],
        )
    )
    st.altair_chart(chart_funnel, use_container_width=True)

# 4) Comparación entre ejecuciones
st.markdown("##### ⚔️ Comparación entre ejecuciones")

if "id_ejecucion" in df_hist.columns:
    opciones = df_hist["id_ejecucion"].tolist()
else:
    # fallback por índice
    df_hist["id_ejecucion"] = df_hist.index.astype(str)
    opciones = df_hist["id_ejecucion"].tolist()

if len(opciones) == 1:
    st.info("Solo hay una ejecución registrada, no es posible comparar aún.")
else:
    col_a, col_b = st.columns(2)

    with col_a:
        ejec_A = st.selectbox("Ejecución A", opciones, index=len(opciones) - 1, key="ejecA")
    with col_b:
        idx_B = max(len(opciones) - 2, 0)
        ejec_B = st.selectbox("Ejecución B", opciones, index=idx_B, key="ejecB")

    fila_A = df_hist[df_hist["id_ejecucion"] == ejec_A].iloc[0]
    fila_B = df_hist[df_hist["id_ejecucion"] == ejec_B].iloc[0]

    col1c, col2c, col3c = st.columns(3)
    with col1c:
        st.metric(
            "Ratio sospecha A",
            formatear_pct(fila_A["ratio_sospecha_global"]),
        )
    with col2c:
        st.metric(
            "Ratio sospecha B",
            formatear_pct(fila_B["ratio_sospecha_global"]),
        )
    with col3c:
        delta_ratio = (
            (fila_B["ratio_sospecha_global"] - fila_A["ratio_sospecha_global"]) * 100
        )
        st.metric("Δ Ratio B vs A (pp)", f"{delta_ratio:+.2f} pp")

    df_cmp = pd.DataFrame(
        {
            "id_ejecucion": [ejec_A, ejec_B],
            "Ratio sospecha (%)": [
                fila_A["ratio_sospecha_global"] * 100,
                fila_B["ratio_sospecha_global"] * 100,
            ],
            "Casos sospechosos": [
                int(fila_A["total_casos_detectados"]),
                int(fila_B["total_casos_detectados"]),
            ],
        }
    )

    # Pasamos a formato largo para que Altair lo lea mejor
    df_cmp_long = df_cmp.melt(
        id_vars="id_ejecucion",
        var_name="Metric",
        value_name="Valor",
    )

    chart_cmp = (
        alt.Chart(df_cmp_long)
        .mark_bar()
        .encode(
            x=alt.X("id_ejecucion:N", title="Ejecución"),
            y=alt.Y("Valor:Q"),
            color=alt.Color("Metric:N", title="Métrica"),
            column=alt.Column("Metric:N", title="Métrica"),
            tooltip=["id_ejecucion", "Metric", "Valor"],
        )
    )

    st.altair_chart(chart_cmp, use_container_width=True)


st.markdown("---")

# ---------------------------------------------
# Tabla final de ejecuciones históricas
# ---------------------------------------------

st.markdown("##### 📋 Detalle de ejecuciones históricas")

df_tabla = df_scope.copy()
df_tabla["Fecha"] = df_tabla["fecha_ejecucion"].dt.strftime("%d/%m/%Y")
df_tabla["Ratio sospecha (%)"] = df_tabla["ratio_sospecha_global"].map(
    lambda x: f"{x*100:.2f}%"
)

cols_show = [
    "Fecha",
    "id_ejecucion",
    "transacciones_totales",
    "total_casos_detectados",
    "casos_multiusuario",
    "casos_self_hedging",
    "Ratio sospecha (%)",
]

st.dataframe(
    df_tabla[cols_show],
    use_container_width=True,
)

# ---------------------------------------------
# Descargas / Exportaciones
# ---------------------------------------------

st.markdown("##### 📁 Descarga de datos")

col_d1, col_d2, col_d3 = st.columns(3)

# 1) Histórico filtrado (todas las ejecuciones dentro del rango de fechas)
with col_d1:
    csv_hist = df_tabla[cols_show].to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="⬇️ Histórico filtrado (CSV)",
        data=csv_hist,
        file_name="historico_riesgo_filtrado.csv",
        mime="text/csv",
    )

# 2) Top usuarios sospechosos (última ejecución)
if top_users:
    with col_d2:
        df_top_u = pd.DataFrame(top_users)
        csv_top_u = df_top_u.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="⬇️ Top usuarios sospechosos (CSV)",
            data=csv_top_u,
            file_name="top_usuarios_sospechosos_ultima_ejecucion.csv",
            mime="text/csv",
        )

# 3) Top eventos bajo lupa (última ejecución)
if top_events:
    with col_d3:
        df_top_e = pd.DataFrame(top_events)
        csv_top_e = df_top_e.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="⬇️ Top eventos bajo lupa (CSV)",
            data=csv_top_e,
            file_name="top_eventos_bajo_lupa_ultima_ejecucion.csv",
            mime="text/csv",
        )
