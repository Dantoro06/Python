from motor_riesgo import (
    cargar_apuestas_desde_excel,
    detectar_abuso_bonos_en_apuestas,
)


def main():
    # Nombre del archivo Excel (el que me acabas de enviar)
    ruta_entrada = "1-10.xlsx"   # cambia el nombre si tu archivo se llama distinto
    ruta_salida = "alertas_riesgo_desde_excel.csv"

    print("Cargando archivo de apuestas:", ruta_entrada)
    df_apuestas = cargar_apuestas_desde_excel(ruta_entrada)
    print(f"Se cargaron {len(df_apuestas)} registros de apuestas.")

    print("Buscando patrones de alto uso de bonos...")

    # Estos parámetros los puedes cambiar después
    df_alertas = detectar_abuso_bonos_en_apuestas(
        df_apuestas,
        min_apuestas_bonus=10,       # mínimo de apuestas con bono
        min_porcentaje_stake_bonus=0.5,  # 0.5 = 50% del stake viene de bonos
    )

    print(f"Se detectaron {len(df_alertas)} jugadores en alerta de abuso de bonos.")

    if len(df_alertas) > 0:
        df_alertas.to_csv(ruta_salida, index=False, encoding="utf-8-sig")
        print("Alertas guardadas en:", ruta_salida)

        # Mostrar un resumen por consola
        columnas_resumen = [
            col for col in [
                "Player Id",
                "Player",
                "n_apuestas",
                "n_apuestas_bonus",
                "porc_apuestas_bonus",
                "porc_stake_bonus",
                "score_riesgo",
                "motivo_alerta",
            ] if col in df_alertas.columns
        ]

        print("\nResumen de primeras alertas:")
        print(df_alertas[columnas_resumen].head().to_string(index=False))
    else:
        print("No se encontraron alertas con los parámetros actuales.")


if __name__ == "__main__":
    main()
