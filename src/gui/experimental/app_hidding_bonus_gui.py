import sys
from pathlib import Path


EXPERIMENTAL_DIR = Path(__file__).resolve().parent
BASE_DIR = EXPERIMENTAL_DIR.parents[1]
MOTOR_DIR = BASE_DIR / "motor"

for path in (EXPERIMENTAL_DIR, MOTOR_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def ejecutar_analisis(self):
    """
    Lógica del botón 'Ejecutar análisis'.
    Lee lo que hay en la caja de texto de archivos, arma la lista,
    llama a las funciones del motor y muestra el log en el cuadro de texto.
    """

    # Limpiar salida y escribir cabecera
    self.txt_salida.delete("1.0", "end")
    self.txt_salida.insert("end", "Iniciando análisis...\n\n")

    try:
        # 1) Construir la lista de archivos a partir de la caja de texto
        #    Siempre debe ser una LISTA de strings, nunca un string suelto.
        texto = self.entry_archivos.get().strip()

        if texto:
            # Si el usuario escribe varios archivos separados por ';'
            lista_archivos = [p.strip() for p in texto.split(";") if p.strip()]
        else:
            # Si la caja está vacía, usamos los archivos por defecto
            from app_hidding_bonus import ARCHIVOS_APUESTAS
            lista_archivos = ARCHIVOS_APUESTAS.copy()

        self.txt_salida.insert("end", "=== Archivos configurados en la lista ===\n")
        self.txt_salida.insert("end", f"{lista_archivos}\n")
        self.txt_salida.insert("end", "=========================================\n\n")
        self.txt_salida.see("end")

        # 2) Cargar apuestas desde los archivos
        from app_hidding_bonus import cargar_apuestas_desde_archivos
        from motor_hidding_bonus import ejecutar_hidding_bonus, ejecutar_self_hedging

        df_apuestas = cargar_apuestas_desde_archivos(lista_archivos)
        if df_apuestas.empty:
            self.txt_salida.insert("end", "No se cargaron apuestas. Revisa los archivos.\n")
            self.txt_salida.see("end")
            return

        # 3) Análisis multiusuario
        self.txt_salida.insert("end", "Ejecutando análisis multiusuario (HiddingBonus)...\n")
        self.txt_salida.see("end")

        df_base, df_multi = ejecutar_hidding_bonus(
            df_apuestas,
            tolerancia_cobertura=0.25,
            min_total_apostado=0.0,
            ruta_base="hidding_bonus_base.csv",
            ruta_multi="hidding_bonus_multiusuario.csv",
        )

        if df_multi is not None and not df_multi.empty:
            self.txt_salida.insert(
                "end",
                f"✔ Tríos multiusuario detectados: {len(df_multi)}\n"
            )
            if "nivel_riesgo_multi" in df_multi.columns:
                self.txt_salida.insert("end", "Distribución por nivel de riesgo (multiusuario):\n")
                self.txt_salida.insert("end", f"{df_multi['nivel_riesgo_multi'].value_counts()}\n\n")
        else:
            self.txt_salida.insert(
                "end",
                "⚠ No se detectaron patrones multi-usuario con las condiciones actuales.\n\n"
            )
        self.txt_salida.see("end")

        # 4) Análisis self-hedging
        self.txt_salida.insert("end", "Ejecutando análisis self-hedging...\n")
        self.txt_salida.see("end")

        df_self = ejecutar_self_hedging(
            df_base,
            ruta_resultados="hidding_bonus_selfhedging.csv",
        )

        if df_self is not None and not df_self.empty:
            self.txt_salida.insert(
                "end",
                f"✔ Self-hedging detectado: {len(df_self)} casos (user+evento).\n"
            )
            if "nivel_riesgo_self" in df_self.columns:
                self.txt_salida.insert("end", "Distribución por nivel de riesgo (self-hedging):\n")
                self.txt_salida.insert("end", f"{df_self['nivel_riesgo_self'].value_counts()}\n\n")
        else:
            self.txt_salida.insert(
                "end",
                "⚠ No se detectaron patrones de self-hedging con las condiciones actuales.\n\n"
            )

        # 5) Listar archivos generados
        self.txt_salida.insert("end", "Archivos CSV generados en la carpeta actual:\n")
        self.txt_salida.insert("end", "  - hidding_bonus_base.csv\n")
        self.txt_salida.insert("end", "  - hidding_bonus_multiusuario.csv\n")
        self.txt_salida.insert("end", "  - hidding_bonus_multiusuario_trios_detalle.csv\n")
        self.txt_salida.insert("end", "  - hidding_bonus_selfhedging.csv\n")
        self.txt_salida.insert("end", "  - hidding_bonus_selfhedging_detalle.csv\n\n")
        self.txt_salida.insert("end", "✔ Análisis completado.\n")
        self.txt_salida.see("end")

    except Exception as e:
        # Mostrar error en el cuadro de texto y en un popup
        import tkinter.messagebox as messagebox
        self.txt_salida.insert("end", "\n[ERROR] Ocurrió una excepción durante la ejecución:\n")
        self.txt_salida.insert("end", f"{e}\n")
        self.txt_salida.see("end")
        messagebox.showerror("Error en ejecución", str(e))
