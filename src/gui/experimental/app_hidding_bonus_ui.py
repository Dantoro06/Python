import io
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


BASE_DIR = Path(__file__).resolve().parents[2]
MOTOR_DIR = BASE_DIR / "motor"

if str(MOTOR_DIR) not in sys.path:
    sys.path.insert(0, str(MOTOR_DIR))

from motor_hidding_bonus import (
    ejecutar_hidding_bonus,
    ejecutar_self_hedging,
)


# ============================================================
# Funciones auxiliares para la UI
# ============================================================

def leer_archivo_subido(uploaded_file) -> pd.DataFrame:
    """
    Lee un archivo subido (CSV o Excel) usando la lógica de separador y decimal.
    Devuelve un DataFrame. Si no se puede leer, devuelve DataFrame vacío.
    """
    filename = uploaded_file.name.lower().strip()

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(
                uploaded_file,
                sep=";",
                decimal=",",
                encoding="utf-8",
                engine="python"
            )
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(uploaded_file, engine="openpyxl")
        else:
            st.error(f"Extensión de archivo no soportada: {uploaded_file.name}")
            return pd.DataFrame()

        return df

    except Exception as e:
        st.error(f"Error al leer {uploaded_file.name}: {e}")
        return pd.DataFrame()


def construir_df_apuestas_desde_ui(uploaded_files) -> pd.DataFrame:
    """
    Concatena todos los archivos subidos en un único DataFrame de apuestas.
    """
    df_list = []
    total_registros = 0

    for f in uploaded_files:
        st.write(f"📄 Cargando archivo: `{f.name}`")
        df = leer_archivo_subido(f)
        if df.empty:
            st.warning(f"El archivo `{f.name}` no tiene datos o no se pudo leer.")
            continue

        registros = len(df)
        total_registros += registros
        st.write(f"→ {registros} registros cargados.")
        df_list.append(df)

    if not df_list:
        return pd.DataFrame()

    df_total = pd.concat(df_list, ignore_index=True)
    st.success(f"✅ Total apuestas cargadas desde todos los archivos: **{total_registros}**")
    return df_total


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """
    Convierte un DataFrame a CSV en memoria (bytes), para usar en download_button.
    """
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, sep=";", decimal=",", encoding="utf-8")
    return buffer.getvalue().encode("utf-8")


# ============================================================
# Interfaz Streamlit
# ============================================================

def main():
    st.set_page_config(page_title="Motor Hidding Bonus", layout="wide")
    st.title("🧠 Motor de Riesgo — HiddingBonus & Self-Hedging")

    st.markdown(
        """
        Interfaz para ejecutar el motor de detección de:
        - **Patrones multiusuario** (tríos 1/X/2 entre usuarios distintos).
        - **Self-hedging** (mismo usuario cubriendo 1/X/2 en el mismo evento).

        Sube uno o varios archivos de apuestas y ajusta los parámetros.
        """
    )

    with st.sidebar:
        st.header("⚙️ Parámetros de análisis")

        tolerancia_cobertura = st.slider(
            "Tolerancia de cobertura (dif. relativa máx. vs total apostado)",
            min_value=0.01,
            max_value=0.50,
            value=0.10,
            step=0.01,
            help=(
                "Cuánto puede diferir la posible ganancia de cada selección "
                "respecto al total apostado entre los 3 implicados. "
                "0.10 = 10% de tolerancia."
            ),
        )

        min_total_apostado = st.number_input(
            "Mínimo total apostado por trío (multiusuario)",
            min_value=0.0,
            max_value=1_000_000.0,
            value=0.0,
            step=10.0,
            help="Tríos con total apostado menor a este valor serán ignorados.",
        )

        st.markdown("---")
        st.caption("Ajusta estos valores según el nivel de sensibilidad de riesgo que quieras.")

    st.subheader("📥 Subir archivos de apuestas")

    uploaded_files = st.file_uploader(
        "Selecciona uno o varios archivos CSV/Excel de apuestas",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
    )

    if not uploaded_files:
        st.info("Sube al menos un archivo para poder ejecutar el análisis.")
        return

    if st.button("🚀 Ejecutar análisis"):
        with st.spinner("Procesando apuestas y ejecutando el motor..."):
            # 1) Construir DataFrame total de apuestas
            df_apuestas = construir_df_apuestas_desde_ui(uploaded_files)

            if df_apuestas.empty:
                st.error("No se cargaron datos de apuestas válidos. Revisa los archivos.")
                return

            # 2) Ejecutar HiddingBonus multiusuario
            st.write("### 🔎 Análisis multiusuario (HiddingBonus)")

            try:
                df_base, df_multi = ejecutar_hidding_bonus(
                    df_apuestas,
                    tolerancia_cobertura=tolerancia_cobertura,
                    min_total_apostado=min_total_apostado,
                    ruta_base="hidding_bonus_base.csv",           # igual se guardan en disco
                    ruta_multi="hidding_bonus_multiusuario.csv",  # pero acá usamos los DataFrames
                )
            except Exception as e:
                st.error(f"Error al ejecutar el análisis multiusuario: {e}")
                return

            if df_multi is not None and not df_multi.empty:
                st.success(f"Se detectaron **{len(df_multi)}** tríos multiusuario (tras filtro de cobertura).")

                # Resumen por nivel de riesgo
                if "nivel_riesgo_multi" in df_multi.columns:
                    resumen_niveles = df_multi["nivel_riesgo_multi"].value_counts()
                    st.write("#### Distribución por nivel de riesgo (multiusuario)")
                    st.dataframe(resumen_niveles.to_frame("cantidad"))

                # Mostrar tabla (limitada) en pantalla
                st.write("#### Ejemplos de tríos detectados (primeros 50)")
                st.dataframe(df_multi.head(50))

                # Botón para descargar todo el resumen
                csv_multi = df_to_csv_bytes(df_multi)
                st.download_button(
                    label="⬇️ Descargar resumen multiusuario (CSV)",
                    data=csv_multi,
                    file_name="hidding_bonus_multiusuario_ui.csv",
                    mime="text/csv",
                )
            else:
                st.warning("No se encontraron tríos multiusuario que cumplan las condiciones.")

            # 3) Ejecutar Self-Hedging sobre la tabla base
            st.write("---")
            st.write("### 🧍‍♂️ Análisis self-hedging (mismo usuario 1/X/2)")

            try:
                df_self = ejecutar_self_hedging(df_base, ruta_resultados="hidding_bonus_selfhedging.csv")
            except Exception as e:
                st.error(f"Error al ejecutar el análisis de self-hedging: {e}")
                return

            if df_self is not None and not df_self.empty:
                st.success(f"Se detectaron **{len(df_self)}** casos de self-hedging (usuario+evento).")

                # Resumen por nivel de riesgo
                if "nivel_riesgo_self" in df_self.columns:
                    resumen_self = df_self["nivel_riesgo_self"].value_counts()
                    st.write("#### Distribución por nivel de riesgo (self-hedging)")
                    st.dataframe(resumen_self.to_frame("cantidad"))

                st.write("#### Ejemplos de casos self-hedging (primeros 50)")
                st.dataframe(df_self.head(50))

                csv_self = df_to_csv_bytes(df_self)
                st.download_button(
                    label="⬇️ Descargar resumen self-hedging (CSV)",
                    data=csv_self,
                    file_name="hidding_bonus_selfhedging_ui.csv",
                    mime="text/csv",
                )
            else:
                st.warning("No se detectaron patrones de self-hedging con las condiciones actuales.")

            st.success("✅ Análisis completado.")


if __name__ == "__main__":
    main()
