import os
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk  # Barra de progreso

import pandas as pd

from motor_hidding_bonus import (
    ejecutar_hidding_bonus,
    ejecutar_self_hedging,
    generar_reporte_json,
)


# -------------------------------------------------------
# Carga de archivos CSV
# -------------------------------------------------------

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
        print("No se cargó ningún archivo de apuestas.\n")
        return pd.DataFrame()

    df_apuestas = pd.concat(dfs, ignore_index=True)
    print(f"\nTOTAL apuestas cargadas desde todos los archivos: {total_registros}\n")
    return df_apuestas


# -------------------------------------------------------
# Redirección de stdout al Text de Tkinter
# -------------------------------------------------------

class TextRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, s):
        self.text_widget.insert(tk.END, s)
        self.text_widget.see(tk.END)
        self.text_widget.update_idletasks()

    def flush(self):
        pass


# -------------------------------------------------------
# Aplicación Tkinter
# -------------------------------------------------------

class MotorHiddingBonusApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Motor Hidding Bonus - Nueve11")

        # --- Frame selección de archivos ---
        frame_files = tk.Frame(root)
        frame_files.pack(fill="x", padx=5, pady=5)

        tk.Label(frame_files, text="Archivos de apuestas a analizar:").pack(
            side="left", padx=(0, 5)
        )

        self.entry_archivos = tk.Entry(frame_files, width=80)
        self.entry_archivos.pack(side="left", fill="x", expand=True)

        btn_sel = tk.Button(
            frame_files,
            text="Seleccionar archivos...",
            command=self.seleccionar_archivos,
        )
        btn_sel.pack(side="left", padx=5)

        # --- Frame parámetros ---
        frame_params = tk.Frame(root)
        frame_params.pack(fill="x", padx=5, pady=5)

        tk.Label(
            frame_params,
            text="Tolerancia cobertura (dif. relativa máx vs total):",
        ).pack(side="left", padx=(0, 5))

        self.entry_tolerancia = tk.Entry(frame_params, width=8)
        self.entry_tolerancia.insert(0, "0.25")
        self.entry_tolerancia.pack(side="left", padx=(0, 10))

        tk.Label(frame_params, text="Mínimo total apostado por trío:").pack(
            side="left", padx=(0, 5)
        )

        self.entry_min_total = tk.Entry(frame_params, width=8)
        self.entry_min_total.insert(0, "0")
        self.entry_min_total.pack(side="left", padx=(0, 10))

        tk.Label(frame_params, text="Máx. apuestas por selección (por evento):").pack(
            side="left", padx=(0, 5)
        )
        self.entry_max_por_sel = tk.Entry(frame_params, width=5)
        self.entry_max_por_sel.insert(0, "20")
        self.entry_max_por_sel.pack(side="left", padx=(0, 10))

        self.btn_run = tk.Button(
            frame_params,
            text="Ejecutar análisis",
            command=self.ejecutar_analisis,
            bg="#4CAF50",
            fg="white",
        )
        self.btn_run.pack(side="left")

        # --- Frame progreso ---
        frame_progress = tk.Frame(root)
        frame_progress.pack(fill="x", padx=5, pady=(0, 5))

        tk.Label(frame_progress, text="Progreso:").pack(side="left", padx=(0, 5))

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            frame_progress,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            variable=self.progress_var,
        )
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.progress_label = tk.Label(frame_progress, text="0%")
        self.progress_label.pack(side="left")

        # --- Frame salida/log ---
        frame_salida = tk.Frame(root)
        frame_salida.pack(fill="both", expand=True, padx=5, pady=5)

        tk.Label(frame_salida, text="Salida / Log del análisis:").pack(
            anchor="w", padx=(0, 5)
        )

        self.txt_salida = scrolledtext.ScrolledText(
            frame_salida, wrap="word", height=25
        )
        self.txt_salida.pack(fill="both", expand=True)

        # Redirigimos stdout a la caja de texto
        self.stdout_original = sys.stdout
        sys.stdout = TextRedirector(self.txt_salida)

    def __del__(self):
        # Restaurar stdout al destruir la app
        try:
            sys.stdout = self.stdout_original
        except Exception:
            pass

    # ------------------------------------
    # Helpers UI
    # ------------------------------------

    def seleccionar_archivos(self):
        rutas = filedialog.askopenfilenames(
            title="Seleccionar archivos de apuestas",
            filetypes=[("CSV", "*.csv"), ("Todos los archivos", "*.*")],
        )
        if not rutas:
            return
        # Guardamos en el entry separados por ';'
        self.entry_archivos.delete(0, tk.END)
        self.entry_archivos.insert(0, ";".join(rutas))

    def _parse_lista_archivos(self, texto: str):
        if not texto.strip():
            return []
        # Aceptamos separadores ';' o ','
        tmp = texto.replace(",", ";")
        rutas = [t.strip() for t in tmp.split(";") if t.strip()]
        return rutas

    def actualizar_progreso(self, fase: str, actual: int, total: int):
        """
        Callback de progreso utilizado por el motor.
        fase: 'multiusuario' o 'selfhedging'
        actual: número de elemento procesado
        total: total de elementos
        """
        if total <= 0:
            return

        porcentaje = int(actual * 100 / total)
        self.progress_var.set(porcentaje)

        if fase == "multiusuario":
            etapa = "Multiusuario"
        elif fase == "selfhedging":
            etapa = "Self-hedging"
        else:
            etapa = fase

        self.progress_label.config(text=f"{etapa}: {porcentaje}%")
        self.root.update_idletasks()

    # ------------------------------------
    # Ejecución del análisis
    # ------------------------------------

    def ejecutar_analisis(self):
        self.txt_salida.delete(1.0, tk.END)
        print("Iniciando análisis...\n")

        # Reset de progreso visual
        self.progress_var.set(0.0)
        self.progress_label.config(text="0%")
        self.root.update_idletasks()

        # 1) Archivos
        texto_archivos = self.entry_archivos.get()
        lista_archivos = self._parse_lista_archivos(texto_archivos)

        if not lista_archivos:
            messagebox.showwarning(
                "Sin archivos",
                "Por favor selecciona al menos un archivo CSV de apuestas.",
            )
            print("⚠ No hay archivos seleccionados.\n")
            return

        # 2) Parámetros
        try:
            tolerancia = float(self.entry_tolerancia.get().strip())
        except ValueError:
            messagebox.showerror(
                "Error en parámetro",
                "La tolerancia de cobertura debe ser un número (ej: 0.10).",
            )
            return

        try:
            min_total = float(self.entry_min_total.get().strip())
        except ValueError:
            messagebox.showerror(
                "Error en parámetro",
                "El mínimo total apostado debe ser un número.",
            )
            return

        try:
            max_por_sel = int(self.entry_max_por_sel.get().strip())
            if max_por_sel <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror(
                "Error en parámetro",
                "El máximo de apuestas por selección debe ser un entero positivo.",
            )
            return

        # 3) Cargar apuestas
        df_apuestas = cargar_apuestas_desde_archivos(lista_archivos)
        if df_apuestas.empty:
            messagebox.showwarning(
                "Sin datos",
                "No se cargaron datos de apuestas (revisa los archivos seleccionados).",
            )
            return

        total_apuestas_original = len(df_apuestas)

        # Medir tiempo de análisis
        t0 = time.time()

        # Deshabilitamos el botón mientras corre el análisis
        self.btn_run.config(state="disabled")
        self.progress_var.set(0.0)
        self.progress_label.config(text="Multiusuario: 0%")
        self.root.update_idletasks()

        df_base = None
        df_multi = None
        df_self = None

        try:
            # 4) Ejecutar análisis multiusuario
            print("Ejecutando análisis multiusuario (HiddingBonus)...")
            try:
                df_base, df_multi = ejecutar_hidding_bonus(
                    df_apuestas,
                    tolerancia_cobertura=tolerancia,
                    min_total_apostado=min_total,
                    ruta_base="hidding_bonus_base.xlsx",
                    ruta_multi="hidding_bonus_multiusuario.xlsx",
                    max_apuestas_por_seleccion=max_por_sel,
                    progress_callback=self.actualizar_progreso,
                )
            except Exception as e:
                print("\n[ERROR] Ocurrió una excepción durante la ejecución:")
                print(e)
                messagebox.showerror("Error en ejecución", str(e))
                return

            if df_multi is not None and not df_multi.empty:
                print(
                    f"✔ Tríos multiusuario detectados (tras filtro de cobertura): "
                    f"{len(df_multi)}"
                )
                if "nivel_riesgo_multi" in df_multi.columns:
                    print("Distribución por nivel de riesgo (multiusuario):")
                    print(df_multi["nivel_riesgo_multi"].value_counts())
            else:
                print("⚠ No se detectaron patrones multiusuario con las condiciones actuales.")

            # Antes de self-hedging, reseteamos ligeramente el texto de progreso
            self.progress_label.config(text="Self-hedging: 0%")
            self.progress_var.set(0.0)
            self.root.update_idletasks()

            # 5) Ejecutar análisis self-hedging
            print("\nEjecutando análisis self-hedging...")
            try:
                df_self = ejecutar_self_hedging(
                    df_base,
                    ruta_resultados="hidding_bonus_selfhedging.xlsx",
                    progress_callback=self.actualizar_progreso,
                )
            except Exception as e:
                print("\n[ERROR] Ocurrió una excepción durante el análisis self-hedging:")
                print(e)
                messagebox.showerror("Error en ejecución", str(e))
                return

            if df_self is not None and not df_self.empty:
                print(
                    f"✔ Self-hedging detectado en {len(df_self)} casos (user+evento).\n"
                )
                if "nivel_riesgo_self" in df_self.columns:
                    print("Distribución por nivel de riesgo (self-hedging):")
                    print(df_self["nivel_riesgo_self"].value_counts())
            else:
                print("⚠ No se detectaron patrones de self-hedging con las condiciones actuales.\n")

            # 6) Resumen de archivos generados (Excel)
            print("\nArchivos Excel generados en la carpeta actual:")
            print(" - hidding_bonus_base.xlsx")
            print(" - hidding_bonus_multiusuario.xlsx")
            print(" - hidding_bonus_multiusuario_trios_detalle.xlsx")
            print(" - hidding_bonus_selfhedging.xlsx")
            print(" - hidding_bonus_selfhedging_detalle.xlsx")
            print("\n✔ Análisis completado.\n")

            tiempo_total = time.time() - t0

            # 7) NUEVO: Generar reporte JSON de riesgo
            try:
                generar_reporte_json(
                    df_base=df_base,
                    df_multi=df_multi,
                    df_self=df_self,
                    archivos_entrada=lista_archivos,
                    total_apuestas_original=total_apuestas_original,
                    tolerancia_cobertura=tolerancia,
                    min_total_apostado=min_total,
                    max_apuestas_por_seleccion=max_por_sel,
                    tiempo_proceso_seg=tiempo_total,
                    nombre_archivo="reporte_riesgo_hiddingbonus.json",
                )
            except Exception as e:
                print("\n[ADVERTENCIA] No se pudo generar el reporte JSON de riesgo:")
                print(e)

            # Progreso final al 100%
            self.progress_var.set(100.0)
            self.progress_label.config(text="Completado: 100%")
            self.root.update_idletasks()

            messagebox.showinfo(
                "Análisis completado",
                "El análisis ha finalizado.\n"
                "Se generaron archivos Excel y el archivo 'reporte_riesgo_hiddingbonus.json' en la carpeta actual.",
            )

        finally:
            # Siempre reactivar el botón al final (éxito o error)
            self.btn_run.config(state="normal")

            # Si querés que la barra vuelva a 0 tras terminar, podrías:
            # self.progress_var.set(0.0)
            # self.progress_label.config(text="0%")
            # self.root.update_idletasks()


if __name__ == "__main__":
    root = tk.Tk()
    app = MotorHiddingBonusApp(root)
    root.mainloop()
