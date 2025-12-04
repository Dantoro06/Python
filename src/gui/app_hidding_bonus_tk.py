import os
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk
import pandas as pd

# ==========================================================
# FIX DE RUTAS INTERNAS DEL PROYECTO
# ==========================================================

# BASE_DIR → carpeta /src
BASE_DIR = Path(__file__).resolve().parents[1]

# PROJECT_ROOT → carpeta principal /Python
PROJECT_ROOT = BASE_DIR.parent

# Insertar rutas si no están presentes
for ruta in (PROJECT_ROOT, BASE_DIR):
    ruta_str = str(ruta)
    if ruta_str not in sys.path:
        sys.path.insert(0, ruta_str)

# Importar el motor desde el paquete correcto
from motor.motor_hidding_bonus import ejecutar_motor_completo


# ==========================================================
# FUNCIONES PRINCIPALES
# ==========================================================

def cargar_apuestas_desde_archivos(lista_archivos):
    print("\n=== Archivos configurados en la lista ===")
    print(lista_archivos)
    print("========================================\n")

    dfs = []
    total_registros = 0

    for ruta in lista_archivos:
        print(f"¿Existe {ruta}? -> {os.path.exists(ruta)}")
        if not os.path.exists(ruta):
            print(f"⚠ No se encontró el archivo ({ruta})\n")
            continue

        try:
            df = pd.read_csv(ruta, sep=",", encoding="utf-8-sig")
            total_registros += len(df)
            dfs.append(df)
            print(f"Cargado correctamente: {len(df)} registros\n")
        except Exception as e:
            print(f"⚠ Error leyendo {ruta}: {e}\n")

    if not dfs:
        print("⚠ No se pudo cargar ningún archivo válido.")
        return None, 0

    df_final = pd.concat(dfs, ignore_index=True)
    print(f"TOTAL apuestas cargadas: {total_registros}\n")

    return df_final, total_registros


# ==========================================================
# INTERFAZ TKINTER (GUI)
# ==========================================================

def ejecutar_analisis(lista_archivos):
    df, total = cargar_apuestas_desde_archivos(lista_archivos)
    if df is None:
        messagebox.showwarning("Advertencia", "No hay archivos válidos para analizar.")
        return

    print("\nEjecutando motor de riesgo...\n")

    try:
        ejecutar_motor_completo(df)
        messagebox.showinfo("Éxito", "El análisis ha finalizado correctamente.")
    except Exception as e:
        messagebox.showerror("Error", f"Error ejecutando motor: {e}")


def construir_gui():
    ventana = tk.Tk()
    ventana.title("Herramienta de Análisis de Riesgo – Nueve11")
    ventana.geometry("900x600")

    frame = ttk.Frame(ventana)
    frame.pack(padx=20, pady=20, fill="both", expand=True)

    label = ttk.Label(frame, text="Archivos CSV para analizar:")
    label.pack()

    caja = scrolledtext.ScrolledText(frame, width=80, height=10)
    caja.pack(pady=10)

    def seleccionar_archivos():
        rutas = filedialog.askopenfilenames(
            title="Seleccionar archivos CSV",
            filetypes=[("CSV Files", "*.csv")]
        )
        if rutas:
            caja.delete("1.0", tk.END)
            for r in rutas:
                caja.insert(tk.END, r + "\n")

    def iniciar_analisis():
        contenido = caja.get("1.0", tk.END).strip().split("\n")
        lista_archivos = [x for x in contenido if x.strip()]

        if not lista_archivos:
            messagebox.showwarning("Advertencia", "No hay archivos para analizar.")
            return

        hilo = threading.Thread(target=ejecutar_analisis, args=(lista_archivos,))
        hilo.start()

    boton_archivos = ttk.Button(frame, text="Seleccionar Archivos", command=seleccionar_archivos)
    boton_archivos.pack()

    boton_analizar = ttk.Button(frame, text="Ejecutar Análisis", command=iniciar_analisis)
    boton_analizar.pack(pady=10)

    ventana.mainloop()


if __name__ == "__main__":
    construir_gui()
