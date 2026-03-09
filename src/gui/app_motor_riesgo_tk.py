# app_motor_riesgo_tk.py
# ==========================================================
# Interfaz Motor de Riesgo Nueve11 (rutas corregidas)
# ==========================================================

import os
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import traceback
import pandas as pd
from datetime import datetime

# ================= FIX RUTAS =================
BASE_DIR = Path(__file__).resolve().parents[1]   # src
PROJECT_ROOT = BASE_DIR.parent                   # Motor Riesgo

for ruta in (PROJECT_ROOT, BASE_DIR):
    ruta_str = str(ruta)
    if ruta_str not in sys.path:
        sys.path.insert(0, ruta_str)

MOTOR_DIR = BASE_DIR / "motor"
if str(MOTOR_DIR) not in sys.path:
    sys.path.insert(0, str(MOTOR_DIR))

# Carpeta de resultados fija (rutas Windows con barras adelante para evitar escapes \U)
REPORTS_DIR = Path("C:/Users/Administrador/OneDrive - Nueve11/Documentos/nueve11/Python/Motor Riesgo/reports")

# ================ IMPORT MOTOR ===============
from motor_bonus_abuse import ejecutar as ejecutar_bonus_abuse
from motor.motor_multi_cuenta import ejecutar_motor_multicuenta
# CAMBIO: AML pipeline y utilidades de carga compartidas
from motor.aml_utils_io import cargar_base_apuestas
from motor.motor_aml_pipeline import ejecutar_aml_pipeline

CONFIG_RIESGO = {
    "umbral_ratio_bono_deposito": 1.5,
    "umbral_horas_bono_retiro": 24,
    "umbral_cantidad_bonos": 3,
}


def construir_gui():
    ventana = tk.Tk()
    ventana.title("Motor de Riesgo - Nueve11")
    ventana.geometry("1100x700")

    # Estilo para botón principal (verde sólido con texto blanco)
    style = ttk.Style(ventana)
    style.theme_use("clam")
    style.configure(
        "Success.TButton",
        foreground="white",
        background="#2e8b57",
        bordercolor="#2e8b57",
        focusthickness=1,
        focuscolor="#2e8b57",
    )
    style.map(
        "Success.TButton",
        foreground=[
            ("disabled", "#e0e0e0"),
            ("pressed", "white"),
            ("active", "white"),
        ],
        background=[
            ("disabled", "#9bb5a7"),
            ("pressed", "#256f45"),
            ("active", "#2f9e62"),
            ("!disabled", "#2e8b57"),
        ],
        bordercolor=[
            ("disabled", "#9bb5a7"),
            ("pressed", "#256f45"),
            ("active", "#2f9e62"),
            ("!disabled", "#2e8b57"),
        ],
    )

    contenedor = ttk.Frame(ventana)
    contenedor.pack(padx=10, pady=10, fill="both", expand=True)

    # Sidebar a la izquierda
    sidebar = ttk.Frame(contenedor, width=280)
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)

    # Área principal a la derecha
    main_area = ttk.Frame(contenedor)
    main_area.pack(side="left", fill="both", expand=True)

    # ----- Categoría: Archivos -----
    archivos_frame = ttk.LabelFrame(sidebar, text="Archivos")
    archivos_frame.pack(fill="x", padx=5, pady=5)

    base_var = tk.StringVar()
    base_rutas: list[str] = []
    base_df_cache = {"df": None}

    ttk.Label(archivos_frame, text="Archivo base estándar:").pack(anchor="w", padx=5, pady=(5, 0))
    entry_base = ttk.Entry(archivos_frame, textvariable=base_var, width=40, state="readonly")
    entry_base.pack(fill="x", padx=5, pady=2)

    def toggle_btn_multi_state():
        # CAMBIO: habilitar tambien AML pipeline
        if base_rutas:
            btn_multi.state(["!disabled"])
            btn_aml.state(["!disabled"])
        else:
            btn_multi.state(["disabled"])
            btn_aml.state(["disabled"])

    def seleccionar_base():
        rutas = filedialog.askopenfilenames(filetypes=[("CSV/Excel", "*.csv *.xlsx *.xls")])
        if rutas:
            base_rutas.clear()
            base_rutas.extend(rutas)
            base_var.set("; ".join(rutas))
            base_df_cache["df"] = None
            toggle_btn_multi_state()

    def limpiar_base():
        base_rutas.clear()
        base_var.set("")
        base_df_cache["df"] = None
        toggle_btn_multi_state()

    ttk.Button(archivos_frame, text="Seleccionar archivo base", command=seleccionar_base).pack(
        padx=5, pady=4, anchor="w", fill="x"
    )
    ttk.Button(archivos_frame, text="Limpiar archivo base", command=limpiar_base).pack(
        padx=5, pady=(0, 6), anchor="w", fill="x"
    )

    # ----- Categoría: Archivos para cruce -----
    cruce_frame = ttk.LabelFrame(sidebar, text="Archivos para cruce")
    cruce_frame.pack(fill="x", padx=5, pady=5)
    ttk.Label(cruce_frame, text="Espacio reservado para futuros cruces.").pack(anchor="w", padx=5, pady=(6, 2))

    # Base de bonos dentro de la sección de cruce
    bonus_var = tk.StringVar()
    ttk.Label(cruce_frame, text="Base de bonos (opcional):").pack(anchor="w", padx=5, pady=(6, 0))
    entry_bonus = ttk.Entry(cruce_frame, textvariable=bonus_var, width=40, state="readonly")
    entry_bonus.pack(fill="x", padx=5, pady=2)

    def seleccionar_bonus():
        ruta = filedialog.askopenfilename(filetypes=[("CSV/Excel", "*.csv *.xlsx *.xls")])
        if ruta:
            bonus_var.set(ruta)

    ttk.Button(cruce_frame, text="Seleccionar base bonos", command=seleccionar_bonus).pack(
        padx=5, pady=4, anchor="w", fill="x"
    )
    ttk.Button(cruce_frame, text="Limpiar base bonos", command=lambda: bonus_var.set("")).pack(
        padx=5, pady=(0, 6), anchor="w", fill="x"
    )

    # CAMBIO: loaders AML opcionales
    depositos_var = tk.StringVar()
    ttk.Label(cruce_frame, text="Base de depositos (opcional):").pack(anchor="w", padx=5, pady=(6, 0))
    ttk.Entry(cruce_frame, textvariable=depositos_var, width=40, state="readonly").pack(
        fill="x", padx=5, pady=2
    )

    def seleccionar_depositos():
        ruta = filedialog.askopenfilename(filetypes=[("CSV/Excel", "*.csv *.xlsx *.xls")])
        if ruta:
            depositos_var.set(ruta)

    ttk.Button(cruce_frame, text="Seleccionar base depositos", command=seleccionar_depositos).pack(
        padx=5, pady=4, anchor="w", fill="x"
    )
    ttk.Button(cruce_frame, text="Limpiar base depositos", command=lambda: depositos_var.set("")).pack(
        padx=5, pady=(0, 6), anchor="w", fill="x"
    )

    retiros_var = tk.StringVar()
    ttk.Label(cruce_frame, text="Base de retiros (opcional):").pack(anchor="w", padx=5, pady=(6, 0))
    ttk.Entry(cruce_frame, textvariable=retiros_var, width=40, state="readonly").pack(
        fill="x", padx=5, pady=2
    )

    def seleccionar_retiros():
        ruta = filedialog.askopenfilename(filetypes=[("CSV/Excel", "*.csv *.xlsx *.xls")])
        if ruta:
            retiros_var.set(ruta)

    ttk.Button(cruce_frame, text="Seleccionar base retiros", command=seleccionar_retiros).pack(
        padx=5, pady=4, anchor="w", fill="x"
    )
    ttk.Button(cruce_frame, text="Limpiar base retiros", command=lambda: retiros_var.set("")).pack(
        padx=5, pady=(0, 6), anchor="w", fill="x"
    )

    kyc_var = tk.StringVar()
    ttk.Label(cruce_frame, text="Base KYC (opcional):").pack(anchor="w", padx=5, pady=(6, 0))
    ttk.Entry(cruce_frame, textvariable=kyc_var, width=40, state="readonly").pack(
        fill="x", padx=5, pady=2
    )

    def seleccionar_kyc():
        ruta = filedialog.askopenfilename(filetypes=[("CSV/Excel", "*.csv *.xlsx *.xls")])
        if ruta:
            kyc_var.set(ruta)

    ttk.Button(cruce_frame, text="Seleccionar base KYC", command=seleccionar_kyc).pack(
        padx=5, pady=4, anchor="w", fill="x"
    )
    ttk.Button(cruce_frame, text="Limpiar base KYC", command=lambda: kyc_var.set("")).pack(
        padx=5, pady=(0, 6), anchor="w", fill="x"
    )

    # ----- Categoría: Análisis de Riesgo -----
    analisis_frame = ttk.LabelFrame(sidebar, text="Análisis de Riesgo")
    analisis_frame.pack(fill="x", padx=5, pady=5)

    btn_bonus = ttk.Button(analisis_frame, text="Motor Bonus Abuse", style="Success.TButton")
    btn_bonus.pack(fill="x", padx=5, pady=(6, 4))

    btn_multi = ttk.Button(
        analisis_frame,
        text="Ejecutar Coberturas 1X2 (Multiusuario + Self-Hedging)",
        style="Success.TButton",
        state="disabled",
    )
    btn_multi.pack(fill="x", padx=5, pady=2)

    # CAMBIO: nuevo boton AML pipeline 2 capas
    btn_aml = ttk.Button(
        analisis_frame,
        text="Ejecutar AML Pipeline (2 capas)",
        style="Success.TButton",
        state="disabled",
    )
    btn_aml.pack(fill="x", padx=5, pady=2)

    # CAMBIO: inputs reutilizados para ratios y tolerancias
    ratio_min_var = tk.StringVar(value="0.03")
    ratio_max_var = tk.StringVar(value="0.05")
    tol_abs_var = tk.StringVar(value="5.0")
    k_var = tk.StringVar(value="0.004")
    tol_max_var = tk.StringVar(value="")

    ratios_frame = ttk.LabelFrame(analisis_frame, text="Ratios margen (profit/stake)")
    ratios_frame.pack(fill="x", padx=5, pady=(6, 4))
    ratios_inputs = ttk.Frame(ratios_frame)
    ratios_inputs.pack(fill="x", padx=4, pady=4)
    ttk.Label(ratios_inputs, text="Min:").pack(side="left")
    ttk.Entry(ratios_inputs, textvariable=ratio_min_var, width=8).pack(side="left", padx=(2, 10))
    ttk.Label(ratios_inputs, text="Max:").pack(side="left")
    ttk.Entry(ratios_inputs, textvariable=ratio_max_var, width=8).pack(side="left", padx=2)

    tol_frame = ttk.LabelFrame(analisis_frame, text="Tolerancia hibrida (monto)")
    tol_frame.pack(fill="x", padx=5, pady=(4, 4))
    tol_inputs = ttk.Frame(tol_frame)
    tol_inputs.pack(fill="x", padx=4, pady=4)
    tol_inputs.columnconfigure(1, weight=1)
    tol_inputs.columnconfigure(3, weight=1)
    ttk.Label(tol_inputs, text="tol_abs:").grid(row=0, column=0, sticky="w")
    ttk.Entry(tol_inputs, textvariable=tol_abs_var, width=10).grid(
        row=0,
        column=1,
        padx=(2, 10),
        sticky="ew",
    )
    ttk.Label(tol_inputs, text="k:").grid(row=0, column=2, sticky="w")
    ttk.Entry(tol_inputs, textvariable=k_var, width=10).grid(
        row=0,
        column=3,
        padx=(2, 10),
        sticky="ew",
    )
    ttk.Label(tol_inputs, text="tol_max (opcional):").grid(row=1, column=0, sticky="w")
    ttk.Entry(tol_inputs, textvariable=tol_max_var, width=10).grid(
        row=1,
        column=1,
        padx=(2, 10),
        sticky="ew",
    )

    ttk.Button(analisis_frame, text="Self-Hedging (próximo)", state="disabled").pack(fill="x", padx=5, pady=2)

    # ----- Categoría: Resultados -----
    resultados_frame = ttk.LabelFrame(sidebar, text="Resultados")
    resultados_frame.pack(fill="x", padx=5, pady=5)

    btn_ultimo = None  # se asigna tras crear el botón

    # Helpers para abrir el último resultado generado
    def obtener_ultimo_reporte():
        if not REPORTS_DIR.exists():
            return None
        archivos = [p for p in REPORTS_DIR.glob("*.xlsx") if p.is_file()]
        if not archivos:
            return None
        return max(archivos, key=lambda p: p.stat().st_mtime)

    def actualizar_estado_ultimo():
        if btn_ultimo is None:
            return
        ultimo = obtener_ultimo_reporte()
        if ultimo:
            btn_ultimo.state(["!disabled"])
        else:
            btn_ultimo.state(["disabled"])

    def abrir_ultimo_reporte():
        ultimo = obtener_ultimo_reporte()
        if not ultimo:
            log.insert(tk.END, "No hay archivos de resultados en reports.\n")
            log.see(tk.END)
            actualizar_estado_ultimo()
            return
        try:
            os.startfile(ultimo)
            log.insert(tk.END, f"Abrir último resultado: {ultimo.name}\n")
        except Exception as e:
            log.insert(tk.END, f"ERROR al abrir último resultado: {e}\n")
        log.see(tk.END)
        actualizar_estado_ultimo()

    def abrir_resultados():
        try:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(REPORTS_DIR)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la carpeta de resultados:\n{e}")

    # ----- Área principal: logs y progreso -----
    log = scrolledtext.ScrolledText(main_area, width=90, height=20, font=("Consolas", 9))
    log.pack(fill="both", expand=True, padx=10, pady=8)

    progress_var = tk.DoubleVar(value=0)
    progress = ttk.Progressbar(main_area, mode="indeterminate", variable=progress_var, maximum=100)
    progress.pack(fill="x", padx=10, pady=(0, 4), anchor="w")
    progress_label = ttk.Label(main_area, text="")
    progress_label.pack(fill="x", padx=10, pady=(0, 10), anchor="w")

    def set_progress_determinate():
        progress.configure(mode="determinate")
        progress_var.set(0)

    def set_progress_indeterminate():
        progress.configure(mode="indeterminate")
        progress_var.set(0)
        progress_label.config(text="")

    def actualizar_progress(fase: str, actual: int, total: int):
        def _update():
            if total and total > 0:
                progress.configure(mode="determinate")
                progress_var.set(min(100, (actual / total) * 100))
            else:
                progress.configure(mode="indeterminate")
            if total and total > 0:
                progress_label.config(text=f"{fase}: {actual}/{total}")
            else:
                progress_label.config(text=fase)
        ventana.after(0, _update)

    def cargar_base_estandar():
        # CAMBIO: reutilizar cargador compartido para mantener misma logica
        if base_df_cache["df"] is not None:
            return base_df_cache["df"]
        if not base_rutas:
            raise ValueError("No hay archivo base seleccionado.")

        def on_csv_unacolumna(ruta, columnas):
            try:
                with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
                    contenido = f.read(200)
            except Exception:
                contenido = ""
            messagebox.showerror(
                "Error de formato CSV",
                "El archivo CSV no esta separado por ';' o se leyo mal. Verifica el separador.",
            )
            print(f"[DEBUG] Columna unica leida: {columnas[0] if columnas else 'N/A'}")
            print(f"[DEBUG] Primeros 200 chars del archivo: {contenido}")

        df_base = cargar_base_apuestas(base_rutas, on_csv_unacolumna=on_csv_unacolumna)
        base_df_cache["df"] = df_base if df_base is not None else pd.DataFrame()
        return base_df_cache["df"]

    # Ejecuta Bonus Abuse con las rutas indicadas (usado por run normal y re-ejecución)
    def ejecutar_bonus_con_rutas(rutas_base: list[str], ruta_bonus: str):
        def tarea():
            try:
                progress.start(10)
                log.insert(tk.END, "Ejecutando Bonus Abuse...\n")

                df_apuestas = cargar_base_estandar().copy()

                if ruta_bonus:
                    if ruta_bonus.lower().endswith(".csv"):
                        df_bonos = pd.read_csv(ruta_bonus)
                    else:
                        df_bonos = pd.read_excel(ruta_bonus)
                else:
                    df_bonos = pd.DataFrame()

                df_res, _ = ejecutar_bonus_abuse(
                    df_apuestas, pd.DataFrame(), df_bonos, pd.DataFrame(), CONFIG_RIESGO
                )

                out = REPORTS_DIR
                out.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                nombre = out / f"bonus_abuse_{timestamp}.xlsx"
                df_res.to_excel(nombre, index=False)

                log.insert(tk.END, f"Finalizado Bonus Abuse. Archivo: {nombre.name}\n")
                log.see(tk.END)
                messagebox.showinfo("OK", "Bonus Abuse finalizado")
                actualizar_estado_ultimo()

            except Exception:
                log.insert(tk.END, "ERROR\n" + traceback.format_exc())
                log.see(tk.END)
            finally:
                progress.stop()
                set_progress_indeterminate()

        threading.Thread(target=tarea, daemon=True).start()

    def lanzar_bonus():
        if not base_rutas:
            messagebox.showwarning("Advertencia", "No hay archivo base seleccionado.")
            return
        ejecutar_bonus_con_rutas(base_rutas.copy(), bonus_var.get().strip())

    btn_bonus.configure(command=lanzar_bonus)

    def lanzar_motor_multicuenta():
        if not base_rutas:
            messagebox.showwarning("Advertencia", "No hay archivo base seleccionado.")
            return

        def tarea():
            try:
                btn_multi.state(["disabled"])
                set_progress_determinate()
                log.insert(tk.END, "Ejecutando Motor Coberturas 1X2 (Multiusuario + Self-Hedging)...\n")
                log.see(tk.END)

                df_base = cargar_base_estandar().copy()

                def cb(fase, actual, total):
                    actualizar_progress(fase, actual, total)

                df_multi, df_self = ejecutar_motor_multicuenta(
                    df_base,
                    tolerancia_cobertura=0.10,
                    min_total_apostado=0.0,
                    max_apuestas_por_seleccion=20,
                    progress_callback=cb,
                )

                set_progress_indeterminate()

                if df_multi is not None and not df_multi.empty:
                    log.insert(tk.END, f"Multiusuario (tríos): {len(df_multi)} casos.\n")
                else:
                    log.insert(tk.END, "Multiusuario (tríos): sin coincidencias.\n")

                if df_self is not None and not df_self.empty:
                    log.insert(tk.END, f"Self-Hedging: {len(df_self)} casos.\n")
                else:
                    log.insert(tk.END, "Self-Hedging: sin casos.\n")

                log.see(tk.END)
                messagebox.showinfo(
                    "Motor completado",
                    "Procesamiento finalizado.\n"
                    "Resultados:\n"
                    "- reports/multi_cuenta_resultado.xlsx\n"
                    "- reports/selfhedging_resultado.xlsx\n"
                    "- reports/reporte_riesgo_multicuenta.json",
                )
                actualizar_estado_ultimo()
            except Exception:
                set_progress_indeterminate()
                log.insert(tk.END, "ERROR\n" + traceback.format_exc())
                log.see(tk.END)
                messagebox.showerror("Error", "Ocurrió un error ejecutando el motor Multi-Cuenta.")
            finally:
                btn_multi.state(["!disabled"])

        threading.Thread(target=tarea, daemon=True).start()

    btn_multi.configure(command=lanzar_motor_multicuenta)
    toggle_btn_multi_state()

    # CAMBIO: ejecutar AML Pipeline (2 capas) sin afectar motores existentes
    def lanzar_aml_pipeline():
        if not base_rutas:
            messagebox.showwarning("Advertencia", "No hay archivo base seleccionado.")
            return

        def parse_float(texto, default):
            try:
                val = (texto or "").replace(",", ".").strip()
                return float(val) if val else default
            except Exception:
                return default

        def tarea():
            try:
                btn_aml.state(["disabled"])
                set_progress_indeterminate()
                progress.start(10)
                log.insert(tk.END, "Ejecutando AML Pipeline (2 capas)...\n")
                log.see(tk.END)

                ratio_min = parse_float(ratio_min_var.get(), 0.03)
                ratio_max = parse_float(ratio_max_var.get(), 0.05)
                if ratio_min > ratio_max:
                    ratio_min, ratio_max = ratio_max, ratio_min

                tol_abs = parse_float(tol_abs_var.get(), 5.0)
                k_val = parse_float(k_var.get(), 0.004)
                tol_max_raw = (tol_max_var.get() or "").replace(",", ".").strip()
                tol_max = float(tol_max_raw) if tol_max_raw else None

                resumen = ejecutar_aml_pipeline(
                    path_base_apuestas=base_rutas,
                    modo_radar_ratio_min=ratio_min,
                    modo_radar_ratio_max=ratio_max,
                    tol_abs=tol_abs,
                    k=k_val,
                    tol_max=tol_max,
                    modo_confirmacion="hybrid",
                    ejecutar_selfhedging=True,
                    path_depositos=depositos_var.get().strip() or None,
                    path_retiros=retiros_var.get().strip() or None,
                    path_kyc=kyc_var.get().strip() or None,
                    out_dir=str(REPORTS_DIR),
                )

                log.insert(
                    tk.END,
                    "AML Pipeline terminado.\n"
                    f"- candidatos_ratio: {resumen.get('total_candidatos_ratio', 0)}\n"
                    f"- confirmados_hybrid: {resumen.get('confirmados_hybrid', 0)}\n"
                    f"- radar: {resumen['salidas'].get('aml_radar_ratio')}\n"
                    f"- cola_operativa: {resumen['salidas'].get('aml_cola_operativa_hybrid')}\n"
                    f"- watchlist: {resumen['salidas'].get('aml_watchlist')}\n"
                    f"- json: {resumen['salidas'].get('aml_pipeline_json')}\n"
                )
                log.see(tk.END)

                messagebox.showinfo(
                    "AML Pipeline finalizado",
                    "Procesamiento finalizado.\n"
                    f"Candidatos ratio: {resumen.get('total_candidatos_ratio', 0)}\n"
                    f"Confirmados hybrid: {resumen.get('confirmados_hybrid', 0)}\n"
                    "Salidas:\n"
                    f"- {resumen['salidas'].get('aml_radar_ratio')}\n"
                    f"- {resumen['salidas'].get('aml_cola_operativa_hybrid')}\n"
                    f"- {resumen['salidas'].get('aml_watchlist')}\n"
                    f"- {resumen['salidas'].get('aml_pipeline_json')}",
                )
                actualizar_estado_ultimo()
            except Exception:
                log.insert(tk.END, "ERROR\n" + traceback.format_exc())
                log.see(tk.END)
                messagebox.showerror("Error", "Ocurrio un error ejecutando AML Pipeline.")
            finally:
                progress.stop()
                set_progress_indeterminate()
                btn_aml.state(["!disabled"])

        threading.Thread(target=tarea, daemon=True).start()

    btn_aml.configure(command=lanzar_aml_pipeline)

    # Botón para abrir el último resultado generado
    btn_ultimo = ttk.Button(resultados_frame, text="Abrir último resultado", command=abrir_ultimo_reporte)
    btn_ultimo.pack(fill="x", padx=5, pady=(6, 4))
    ttk.Button(resultados_frame, text="Abrir carpeta de resultados", command=abrir_resultados).pack(
        fill="x", padx=5, pady=6
    )
    actualizar_estado_ultimo()

    ventana.mainloop()


if __name__ == "__main__":
    construir_gui()
