import os
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from motor.motor_hidding_bonus import ejecutar_motor_completo


def cargar_apuestas_desde_archivos(lista_archivos):
    print("\n=== Archivos configurados en la lista ===")
    print(lista_archivos)
    print("=========================================\n")

    dfs = []
    total_registros = 0

    for ruta in lista_archivos:
        print(f"¿Existe {ruta}? -> {os.path.exists(ruta)}")
        if not os.path.exists(ruta):
            print(f"  ⚠ No se encontró el archivo {ruta}\n")
            continue

        df = None

        # 1) Intento inicial: formato tipo europeo ; , utf-8-sig
        try:
            df = pd.read_csv(ruta, sep=";", decimal=",", encoding="utf-8-sig")
            print(f"  → CSV cargado correctamente: {len(df)} registros (sep=';' utf-8-sig)")

            # Si solo hay una columna y el nombre contiene comas, el separador real es ','
            if len(df.columns) == 1 and isinstance(df.columns[0], str) and "," in df.columns[0]:
                print("  → Detectado separador ',', recargando con sep=',' ...")
                df = pd.read_csv(ruta, sep=",", decimal=".", encoding="utf-8-sig")
                print(f"  → CSV recargado correctamente: {len(df)} registros (sep=',' utf-8-sig)")
        except Exception as e1:
            print(f"  ⚠ Error leyendo {ruta} con sep=';' utf-8-sig -> {e1}")
            # 2) Segundo intento: coma + utf-8-sig
            try:
                df = pd.read_csv(ruta, sep=",", decimal=".", encoding="utf-8-sig")
                print(f"  → CSV cargado correctamente: {len(df)} registros (sep=',' utf-8-sig)")
            except Exception as e2:
                print(f"  ⚠ Error con utf-8-sig, intentando latin1 -> {e2}")
                # 3) Último intento: coma + latin1
                df = pd.read_csv(ruta, sep=",", decimal=".", encoding="latin1")
                print(f"  → CSV cargado correctamente: {len(df)} registros (sep=',' latin1)")

        dfs.append(df)
        total_registros += len(df)
        print(f"  → {len(df)} registros cargados\n")

    if not dfs:
        print("⚠ No se cargó ningún archivo de apuestas.\n")
        return pd.DataFrame()

    df_apuestas = pd.concat(dfs, ignore_index=True)
    print(f"\nTOTAL apuestas cargadas: {total_registros}\n")
    return df_apuestas


class TextRedirector:
    def __init__(self, widget):
        self.widget = widget

    def write(self, text):
        self.widget.insert(tk.END, text)
        self.widget.see(tk.END)

    def flush(self):
        pass


class MotorHiddingBonusApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Motor Hidding Bonus - Nueve11")

        self.ruta_bonus = None

        frame_files = tk.Frame(root)
        frame_files.pack(fill="x", padx=5, pady=5)

        tk.Label(frame_files, text="Archivos de apuestas:").pack(side="left")

        self.entry_archivos = tk.Entry(frame_files, width=80)
        self.entry_archivos.pack(side="left", padx=5, expand=True, fill="x")

        tk.Button(
            frame_files,
            text="Seleccionar archivos...",
            command=self.seleccionar_archivos
        ).pack(side="left")

        frame_bonus = tk.Frame(root)
        frame_bonus.pack(fill="x", padx=5, pady=5)

        tk.Label(frame_bonus, text="Archivo usuarios con BONUS:").pack(side="left")

        self.lbl_bonus = tk.Label(frame_bonus, text="(ninguno)")
        self.lbl_bonus.pack(side="left", padx=5)

        tk.Button(
            frame_bonus,
            text="Seleccionar archivo bonus...",
            command=self.seleccionar_bonus
        ).pack(side="left")

        frame_params = tk.Frame(root)
        frame_params.pack(fill="x", padx=5, pady=5)

        tk.Label(frame_params, text="Tolerancia cobertura:").pack(side="left")
        self.entry_tolerancia = tk.Entry(frame_params, width=6)
        self.entry_tolerancia.insert(0, "0.25")
        self.entry_tolerancia.pack(side="left", padx=5)

        tk.Label(frame_params, text="Mínimo total apostado:").pack(side="left")
        self.entry_min_total = tk.Entry(frame_params, width=6)
        self.entry_min_total.insert(0, "0")
        self.entry_min_total.pack(side="left", padx=5)

        tk.Label(frame_params, text="Máx. apuestas por selección:").pack(side="left")
        self.entry_max_por_sel = tk.Entry(frame_params, width=4)
        self.entry_max_por_sel.insert(0, "20")
        self.entry_max_por_sel.pack(side="left", padx=5)

        self.btn_run = tk.Button(
            frame_params,
            text="Ejecutar análisis",
            bg="#4CAF50",
            fg="white",
            command=self.thread_ejecutar
        )
        self.btn_run.pack(side="left", padx=10)

        frame_prog = tk.Frame(root)
        frame_prog.pack(fill="x", padx=5, pady=5)

        tk.Label(frame_prog, text="Progreso:").pack(side="left")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            frame_prog,
            variable=self.progress_var,
            maximum=100
        )
        self.progress_bar.pack(side="left", expand=True, fill="x", padx=5)
        self.progress_label = tk.Label(frame_prog, text="0%")
        self.progress_label.pack(side="left")

        frame_log = tk.Frame(root)
        frame_log.pack(fill="both", expand=True, padx=5, pady=5)

        self.txt_salida = scrolledtext.ScrolledText(frame_log, wrap="word", height=25)
        self.txt_salida.pack(fill="both", expand=True)

        sys.stdout = TextRedirector(self.txt_salida)

    def seleccionar_archivos(self):
        rutas = filedialog.askopenfilenames(
            title="Seleccionar archivos de apuestas",
            filetypes=[("CSV", "*.csv"), ("Todos los archivos", "*.*")]
        )
        if rutas:
            self.entry_archivos.delete(0, tk.END)
            self.entry_archivos.insert(0, ";".join(rutas))

    def seleccionar_bonus(self):
        ruta = filedialog.askopenfilename(
            title="Seleccionar archivo BONUS",
            filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx *.xls"), ("Todos", "*.*")]
        )
        if ruta:
            self.ruta_bonus = ruta
            self.lbl_bonus.config(text=os.path.basename(ruta))
            print(f"Archivo BONUS seleccionado: {ruta}\n")

    def thread_ejecutar(self):
        self.btn_run.config(state="disabled")
        self.progress_var.set(0)
        self.progress_label.config(text="0%")
        self.txt_salida.delete(1.0, tk.END)

        hilo = threading.Thread(target=self.worker_analisis, daemon=True)
        hilo.start()

    def actualizar_progreso(self, fase, actual, total):
        if total <= 0:
            return
        porc = int(actual * 100 / total)
        self.progress_var.set(porc)
        self.progress_label.config(text=f"{fase}: {porc}%")
        self.root.update_idletasks()

    def worker_analisis(self):
        try:
            print("Iniciando análisis...\n")

            rutas = self.entry_archivos.get().strip()
            if not rutas:
                print("⚠ No hay archivos de apuestas.")
                messagebox.showwarning("Sin archivos", "Selecciona archivos CSV.")
                return

            lista_archivos = [r.strip() for r in rutas.split(";") if r.strip()]
            df_apuestas = cargar_apuestas_desde_archivos(lista_archivos)

            print(f"Columnas originales: {list(df_apuestas.columns)}")

            if df_apuestas.empty:
                messagebox.showwarning("Sin datos", "No se cargaron apuestas.")
                return

            # Normalizar columna de usuario -> 'userid'
            cols_norm = {
                str(c)
                .replace("\ufeff", "")
                .replace("ï»¿", "")
                .lower()
                .strip()
                .replace(" ", "")
                .replace("-", "")
                .replace("_", ""): c
                for c in df_apuestas.columns
            }

            posibles_usuario = ["playerid", "player_id", "userid", "user_id", "player id"]

            col_usuario_real = None
            for target in posibles_usuario:
                clave = target.replace(" ", "").replace("-", "").replace("_", "")
                if clave in cols_norm:
                    col_usuario_real = cols_norm[clave]
                    break

            if col_usuario_real is None:
                raise ValueError(
                    f"No se encontró ninguna columna de usuario en el CSV. "
                    f"Columnas recibidas: {list(df_apuestas.columns)}"
                )

            if col_usuario_real != "userid":
                df_apuestas.rename(columns={col_usuario_real: "userid"}, inplace=True)

            print(f"Columna de usuario detectada: {col_usuario_real} -> renombrada a 'userid'")
            print(f"Columnas después de normalizar: {list(df_apuestas.columns)}\n")

            tol = float(self.entry_tolerancia.get())
            min_total = float(self.entry_min_total.get())
            max_sel = int(self.entry_max_por_sel.get())

            print("Ejecutando MOTOR COMPLETO...\n")

            df_base, df_multi, df_self = ejecutar_motor_completo(
                df_apuestas=df_apuestas,
                ruta_bonus=self.ruta_bonus,
                tolerancia_cobertura=tol,
                min_total_apostado=min_total,
                max_apuestas_por_seleccion=max_sel,
            )

            print("\n✔ Proceso completado.\n")

        except Exception as e:
            print("\n[ERROR]")
            print(e)
            messagebox.showerror("Error", str(e))

        finally:
            self.btn_run.config(state="normal")
            self.progress_var.set(100)
            self.progress_label.config(text="100%")
            self.root.update_idletasks()


if __name__ == "__main__":
    root = tk.Tk()
    app = MotorHiddingBonusApp(root)
    root.mainloop()
