import os
import time
import pandas as pd

from motor_hidding_bonus import (
    ejecutar_hidding_bonus,
    ejecutar_self_hedging,
    generar_reporte_json,
)


# -------------------------------------------------------------------
# Configuración: lista de archivos de apuestas a analizar
# -------------------------------------------------------------------
ARCHIVOS_APUESTAS = [
    "apuestas_big_test_part1.csv",
    "apuestas_big_test_part2.csv",
    "apuestas_selfhedging_test.csv",
]


def cargar_apuestas_desde_archivos(lista_archivos):
    print("=== Archivos configurados en la lista ===")
    print(lista_archivos)
    print("=========================================\n")

    dfs = []
    total_registros = 0

    for nombre in lista_archivos:
        print(f"¿Existe {nombre}? -> {os.path.exists(nombre)}")
        if not os.path.exists(nombre):
            print(f"  ⚠ No se encontró el archivo {nombre}\n")
            continue

        try:
            # Intentamos leer asumiendo ; como separador y , como decimal
            df = pd.read_csv(nombre, sep=";", decimal=",")
            print(f"  → CSV cargado correctamente: {len(df)} registros")
        except Exception as e:
            print(f"  ⚠ Error leyendo {nombre} con sep=';' decimal=',' -> {e}")
            print("  → Intentando con sep=',' decimal='.' ...")
            df = pd.read_csv(nombre, sep=",", decimal=".")
            print(f"  → CSV cargado correctamente: {len(df)} registros")

        dfs.append(df)
        total_registros += len(df)
        print(f"  → {len(df)} registros cargados\n")

    if not dfs:
        print("No se cargó ningún archivo de apuestas. Saliendo.")
        return pd.DataFrame()

    df_apuestas = pd.concat(dfs, ignore_index=True)
    print(f"\nTOTAL apuestas cargadas desde todos los archivos: {total_registros}\n")
    return df_apuestas


def main():
    # 1) Cargar apuestas (CSV)
    df_apuestas = cargar_apuestas_desde_archivos(ARCHIVOS_APUESTAS)
    if df_apuestas.empty:
        return

    total_apuestas_original = len(df_apuestas)

    # Medir tiempo total de proceso
    t0 = time.time()

    # 2) Ejecutar motor Hidding Bonus (multiusuario)
    print("Preparando tabla base y ejecutando análisis multiusuario...")

    tolerancia_cobertura = 0.25
    min_total_apostado = 0.0
    max_apuestas_por_seleccion = 20  # coincide con default del motor

    try:
        df_base, df_multi = ejecutar_hidding_bonus(
            df_apuestas,
            tolerancia_cobertura=tolerancia_cobertura,      # umbral de cobertura
            min_total_apostado=min_total_apostado,          # puedes ajustar si quieres
            ruta_base="hidding_bonus_base.xlsx",
            ruta_multi="hidding_bonus_multiusuario.xlsx",
            max_apuestas_por_seleccion=max_apuestas_por_seleccion,
        )
    except Exception as e:
        print("\n[ERROR] Ocurrió un error al ejecutar el análisis multiusuario:")
        print(e)
        return

    # 3) Ejecutar self-hedging usando df_base ya preparado
    print("\nEjecutando análisis self-hedging...")

    try:
        df_self = ejecutar_self_hedging(
            df_base,
            ruta_resultados="hidding_bonus_selfhedging.xlsx",
        )
    except Exception as e:
        print("\n[ERROR] Ocurrió un error al ejecutar el análisis de self-hedging:")
        print(e)
        return

    tiempo_total = time.time() - t0

    # 4) Resumen en consola
    print("\n=== RESUMEN EJECUCIÓN ===")
    print(f"Apuestas en tabla base: {len(df_base)}")

    if df_multi is not None and not df_multi.empty:
        print(f"Tríos multi-usuario detectados: {len(df_multi)}")
        if "nivel_riesgo_multi" in df_multi.columns:
            print("\n[Multiusuario] Distribución por nivel de riesgo:")
            print(df_multi["nivel_riesgo_multi"].value_counts())
    else:
        print("No se detectaron patrones multi-usuario con las condiciones actuales.")

    if df_self is not None and not df_self.empty:
        print(f"\nPatrones self-hedging detectados: {len(df_self)}")
        if "nivel_riesgo_self" in df_self.columns:
            print("\n[Self-hedging] Distribución por nivel de riesgo:")
            print(df_self["nivel_riesgo_self"].value_counts())
    else:
        print("\nNo se detectaron patrones de self-hedging con las condiciones actuales.")

    print("\nArchivos Excel generados:")
    print("  - hidding_bonus_base.xlsx")
    print("  - hidding_bonus_multiusuario.xlsx")
    print("  - hidding_bonus_multiusuario_trios_detalle.xlsx")
    print("  - hidding_bonus_selfhedging.xlsx")
    print("  - hidding_bonus_selfhedging_detalle.xlsx")

    # 5) NUEVO: Generar reporte JSON de riesgo
    try:
        generar_reporte_json(
            df_base=df_base,
            df_multi=df_multi,
            df_self=df_self,
            archivos_entrada=ARCHIVOS_APUESTAS,
            total_apuestas_original=total_apuestas_original,
            tolerancia_cobertura=tolerancia_cobertura,
            min_total_apostado=min_total_apostado,
            max_apuestas_por_seleccion=max_apuestas_por_seleccion,
            tiempo_proceso_seg=tiempo_total,
            nombre_archivo="reporte_riesgo_hiddingbonus.json",
        )
    except Exception as e:
        print("\n[ADVERTENCIA] No se pudo generar el reporte JSON de riesgo:")
        print(e)

    print("\nProceso completado.")


if __name__ == "__main__":
    main()
