
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

# Insertar rutas base en sys.path si no están presentes
for ruta in (PROJECT_ROOT, BASE_DIR):
    ruta_str = str(ruta)
    if ruta_str not in sys.path:
        sys.path.insert(0, ruta_str)

# Directorio del motor (src/motor)  # CAMBIO
MOTOR_DIR = BASE_DIR / "motor"      # CAMBIO
if str(MOTOR_DIR) not in sys.path:  # CAMBIO
    sys.path.insert(0, str(MOTOR_DIR))  # CAMBIO

# Importar el motor desde el módulo correcto  # CAMBIO
from motor_hidding_bonus import ejecutar_motor_completo  # CAMBIO


# ==========================================================
# CARGA DE APUESTAS
# ==========================================================

def cargar_apuestas_desde_archivos(lista_archivos):
    """
    Carga todos los CSV de la lista y los concatena en un solo DataFrame.
    Devuelve (df_final, total_registros) o (None, 0) si no se cargó nada.
    """
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
# EJECUCIÓN DEL ANÁLISIS (CON MOTOR)
# ==========================================================

def ejecutar_analisis(
    lista_archivos,
    ruta_bonus,
    boton_analizar,
    progress_bar,
    ventana,
    tolerancia_cobertura,
    min_total_apostado,
    max_apuestas_por_seleccion,
):
    """
    Ejecuta el análisis en un hilo de fondo, controlando:
      - logs básicos en consola,
      - messagebox de éxito/error,
      - y SIEMPRE reactivando el botón y dejando la barra en 100%.

    ruta_bonus puede ser None o cadena vacía si no se desea cruzar con bonos.
    """
    try:
        # Deshabilitar botón y preparar barra de progreso
        boton_analizar.config(state="disabled")  # CAMBIO
        if progress_bar is not None:             # CAMBIO
            progress_bar["value"] = 0            # CAMBIO
            progress_bar.start(10)               # CAMBIO: modo indeterminado

        print("\n[GUI] Iniciando carga de archivos...\n")  # CAMBIO
        df, total = cargar_apuestas_desde_archivos(lista_archivos)
        if df is None:
            print("[GUI] No hay archivos válidos para analizar.\n")  # CAMBIO
            messagebox.showwarning(
                "Advertencia",
                "No hay archivos válidos para analizar.",
                parent=ventana,
            )
            return

        print(f"[GUI] Total de registros cargados: {total}")  # CAMBIO
        print("\n[GUI] Ejecutando motor de riesgo...\n")       # CAMBIO

        # Normalizar ruta de bonos (puede ser opcional)  # CAMBIO
        ruta_bonus_norm = (ruta_bonus or "").strip()          # CAMBIO
        if ruta_bonus_norm == "":                             # CAMBIO
            ruta_bonus_norm = None                            # CAMBIO

        # Llamar al motor con o sin base de bonos             # CAMBIO
        ejecutar_motor_completo(
            df,
            ruta_bonus=ruta_bonus_norm,
            tolerancia_cobertura=tolerancia_cobertura,
            min_total_apostado=min_total_apostado,
            max_apuestas_por_seleccion=max_apuestas_por_seleccion,
        )

        print("\n[GUI] Motor finalizado sin errores.\n")  # CAMBIO
        messagebox.showinfo(
            "Éxito",
            "El análisis ha finalizado correctamente.",
            parent=ventana,
        )

    except Exception as e:
        # Log de error en consola y en popup
        print("\n[GUI][ERROR] Ocurrió un error durante el análisis:\n")  # CAMBIO
        print(e)  # CAMBIO
        messagebox.showerror(
            "Error",
            f"Error ejecutando el motor de riesgo:\n{e}",
            parent=ventana,
        )
    finally:
        # Garantizar que el botón y la barra de progreso se restablecen
        try:
            if progress_bar is not None:  # CAMBIO
                progress_bar.stop()       # CAMBIO
                progress_bar["value"] = 100  # CAMBIO

            boton_analizar.config(state="normal")  # CAMBIO
            ventana.update_idletasks()             # CAMBIO
        except Exception as e_final:
            # En caso de cualquier problema al reactivar la UI, solo lo registramos
            print("[GUI][ADVERTENCIA] Error al restablecer la interfaz:", e_final)  # CAMBIO


# ==========================================================
# INTERFAZ TKINTER (GUI)
# ==========================================================

def construir_gui():
    ventana = tk.Tk()
    ventana.title("Herramienta de Análisis de Riesgo – Nueve11")
    ventana.geometry("900x700")  # un poco más alta para la barra y bonos  # CAMBIO

    frame = ttk.Frame(ventana)
    frame.pack(padx=20, pady=20, fill="both", expand=True)

    # ------------------ Parámetros configurables ------------------
    parametros_frame = ttk.Frame(frame)
    parametros_frame.pack(fill="x", pady=(0, 10))

    tolerancia_var = tk.StringVar(value="0.25")
    min_total_var = tk.StringVar(value="0")
    max_apuestas_var = tk.StringVar(value="20")

    # Fila 1: Tolerancia cobertura
    ttk.Label(parametros_frame, text="Tolerancia cobertura:").grid(
        row=0, column=0, sticky="w", padx=(0, 5), pady=2
    )
    ttk.Entry(parametros_frame, textvariable=tolerancia_var, width=10).grid(
        row=0, column=1, sticky="w", padx=(0, 15), pady=2
    )

    # Fila 2: Mínimo total apostado
    ttk.Label(parametros_frame, text="Mínimo total apostado:").grid(
        row=1, column=0, sticky="w", padx=(0, 5), pady=2
    )
    ttk.Entry(parametros_frame, textvariable=min_total_var, width=10).grid(
        row=1, column=1, sticky="w", padx=(0, 15), pady=2
    )

    # Fila 3: Máx. apuestas por selección
    ttk.Label(parametros_frame, text="Máx. apuestas por selección:").grid(
        row=2, column=0, sticky="w", padx=(0, 5), pady=2
    )
    ttk.Entry(parametros_frame, textvariable=max_apuestas_var, width=10).grid(
        row=2, column=1, sticky="w", padx=(0, 15), pady=2
    )

    # ------------------ Archivos de apuestas ------------------
    label = ttk.Label(frame, text="Archivos CSV de apuestas para analizar:")
    label.pack()

    caja_apuestas = scrolledtext.ScrolledText(frame, width=80, height=10)
    caja_apuestas.pack(pady=10)

    # ------------------ Archivo de bonos (opcional) ------------------  # CAMBIO
    bonus_var = tk.StringVar()  # CAMBIO

    bonus_frame = ttk.Frame(frame)  # CAMBIO
    bonus_frame.pack(fill="x", pady=(5, 10))  # CAMBIO

    bonus_label = ttk.Label(
        bonus_frame,
        text="Archivo de base de bonos (opcional):"
    )  # CAMBIO
    bonus_label.pack(anchor="w")  # CAMBIO

    entry_frame = ttk.Frame(bonus_frame)  # CAMBIO
    entry_frame.pack(fill="x")            # CAMBIO

    bonus_entry = ttk.Entry(
        entry_frame,
        textvariable=bonus_var,
        width=80
    )  # CAMBIO
    bonus_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))  # CAMBIO

    def seleccionar_archivo_bonus():  # CAMBIO
        ruta = filedialog.askopenfilename(
            title="Seleccionar base de bonos",
            filetypes=[
                ("Archivos Excel", "*.xlsx;*.xls"),
                ("Archivos CSV", "*.csv"),
                ("Todos los archivos", "*.*"),
            ],
        )
        if ruta:
            bonus_var.set(ruta)

    boton_bonus = ttk.Button(
        entry_frame,
        text="Seleccionar base de bonos",
        command=seleccionar_archivo_bonus,
    )  # CAMBIO
    boton_bonus.pack(side="left")  # CAMBIO

    # ------------------ Barra de progreso ------------------  # CAMBIO
    progress_bar = ttk.Progressbar(frame, mode="indeterminate")  # CAMBIO
    progress_bar.pack(fill="x", pady=(5, 10))  # CAMBIO

    # ------------------ Funciones internas de la GUI ------------------

    def seleccionar_archivos():
        rutas = filedialog.askopenfilenames(
            title="Seleccionar archivos CSV de apuestas",
            filetypes=[("CSV Files", "*.csv")]
        )
        if rutas:
            caja_apuestas.delete("1.0", tk.END)
            for r in rutas:
                caja_apuestas.insert(tk.END, r + "\n")

    def iniciar_analisis():
        contenido = caja_apuestas.get("1.0", tk.END).strip().split("\n")
        lista_archivos = [x for x in contenido if x.strip()]

        if not lista_archivos:
            messagebox.showwarning("Advertencia", "No hay archivos de apuestas para analizar.")
            return

        ruta_bonus = bonus_var.get()

        try:
            tolerancia_cobertura = float(tolerancia_var.get() or "0.25")
        except ValueError:
            tolerancia_cobertura = 0.25

        try:
            min_total_apostado = float(min_total_var.get() or "0")
        except ValueError:
            min_total_apostado = 0.0

        try:
            max_apuestas_por_seleccion = int(max_apuestas_var.get() or "20")
        except ValueError:
            max_apuestas_por_seleccion = 20

        # Lanzar el análisis en un hilo de fondo, pasando botón y barra  # CAMBIO
        hilo = threading.Thread(
            target=ejecutar_analisis,
            args=(
                lista_archivos,
                ruta_bonus,
                boton_analizar,
                progress_bar,
                ventana,
                tolerancia_cobertura,
                min_total_apostado,
                max_apuestas_por_seleccion,
            ),
            daemon=True,  # CAMBIO: hilo daemon para que no bloquee cierre
        )
        hilo.start()

    # ------------------ Botones principales ------------------

    boton_archivos = ttk.Button(frame, text="Seleccionar Archivos", command=seleccionar_archivos)
    boton_archivos.pack()

    boton_analizar = ttk.Button(frame, text="Ejecutar Análisis", command=iniciar_analisis)
    boton_analizar.pack(pady=10)

    ventana.mainloop()


if __name__ == "__main__":
    construir_gui()
