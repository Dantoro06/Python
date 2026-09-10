# -*- coding: utf-8 -*-
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

# CAMBIO (enero 2026):
# - Se agregan campos de tolerancia híbrida (tol_abs, k, tol_max) y modo hybrid/ratio.
# - Se pasan los nuevos parámetros al motor multi-cuenta manteniendo compatibilidad con ratios previos.
# - Se mantiene la configuración y flujos existentes del panel.
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

# ================ IMPORT MOTOR ===============
from motor_bonus_abuse import ejecutar as ejecutar_bonus_abuse
# CAMBIO: AML pipeline y utilidades de carga compartidas
try:
    from motor.aml_utils_io import cargar_base_apuestas, cargar_tabla_opcional
except Exception:
    from src.motor.aml_utils_io import cargar_base_apuestas, cargar_tabla_opcional
try:
    from utils.paths_dashboard import DASHBOARD_DATA_DIR, REPORTS_DIR
except Exception:
    from src.utils.paths_dashboard import DASHBOARD_DATA_DIR, REPORTS_DIR
from motor.motor_aml_pipeline import ejecutar_aml_pipeline
try:
    from motor.motor_aml_pipeline_v0 import ejecutar_pipeline_aml_v0
except Exception:
    from src.motor.motor_aml_pipeline_v0 import ejecutar_pipeline_aml_v0

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

    SIDEBAR_WIDTH = 360
    SIDEBAR_WRAP = SIDEBAR_WIDTH - 30

    contenedor = ttk.Frame(ventana)
    contenedor.pack(padx=10, pady=10, fill="both", expand=True)

    # Sidebar a la izquierda (con scroll vertical)
    sidebar_container = ttk.Frame(contenedor)
    sidebar_container.pack(side="left", fill="y")

    sidebar_canvas = tk.Canvas(sidebar_container, width=SIDEBAR_WIDTH, highlightthickness=0)
    sidebar_scroll = ttk.Scrollbar(sidebar_container, orient="vertical", command=sidebar_canvas.yview)
    sidebar_canvas.configure(yscrollcommand=sidebar_scroll.set)

    sidebar_canvas.pack(side="left", fill="y", expand=False)
    sidebar_scroll.pack(side="right", fill="y")

    sidebar = ttk.Frame(sidebar_canvas)
    sidebar_window = sidebar_canvas.create_window((0, 0), window=sidebar, anchor="nw")

    def _sync_sidebar_width(event):
        sidebar_canvas.itemconfigure(sidebar_window, width=SIDEBAR_WIDTH)

    def _sync_sidebar_scroll(event):
        sidebar_canvas.configure(scrollregion=sidebar_canvas.bbox("all"))

    sidebar.bind("<Configure>", _sync_sidebar_scroll)
    sidebar_canvas.bind("<Configure>", _sync_sidebar_width)

    def _scroll_sidebar_mousewheel(event):
        # Comprobar el widget bajo el cursor, incluso sobre hijos del sidebar.
        widget = ventana.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget == sidebar_container:
                if event.delta:
                    steps = -int(event.delta / 120)
                    if steps == 0:
                        steps = -1 if event.delta > 0 else 1
                    sidebar_canvas.yview_scroll(steps, "units")
                return "break"
            widget = widget.master

    ventana.bind("<MouseWheel>", _scroll_sidebar_mousewheel, add="+")

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
            btn_pipeline_v0.state(["!disabled"])
        else:
            btn_multi.state(["disabled"])
            btn_aml.state(["disabled"])
            btn_pipeline_v0.state(["disabled"])

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
        text="Ejecutar Coberturas 1X2\n(Multiusuario + Self-Hedging)",
        style="Success.TButton",
        state="disabled",
    )
    btn_multi.pack(fill="x", padx=5, pady=2)

    # CAMBIO: boton para smoke test de coberturas
    btn_smoke = ttk.Button(
        analisis_frame,
        text="SMOKE TEST COBERTURAS",
        style="Success.TButton",
    )
    btn_smoke.pack(fill="x", padx=5, pady=2)

    # CAMBIO: nuevo boton AML pipeline 2 capas
    btn_aml = ttk.Button(
        analisis_frame,
        text="Ejecutar AML Pipeline (2 capas)",
        style="Success.TButton",
        state="disabled",
    )
    btn_aml.pack(fill="x", padx=5, pady=2)

    btn_pipeline_v0 = ttk.Button(
        analisis_frame,
        text="Ejecutar PIPELINE AML v0 (Bonus Abuse + Coberturas)",
        style="Success.TButton",
        state="disabled",
    )
    btn_pipeline_v0.pack(fill="x", padx=5, pady=2)

    ratio_min_var = tk.StringVar(value="0.03")
    ratio_max_var = tk.StringVar(value="0.05")
    tol_abs_var = tk.StringVar(value="5.0")
    k_var = tk.StringVar(value="0.004")
    tol_max_var = tk.StringVar(value="")
    modo_tol_var = tk.StringVar(value="hybrid")
    run_ratio_var = tk.BooleanVar(value=True)

    ratios_frame = ttk.LabelFrame(analisis_frame, text="Ratios margen (profit/stake)")
    ratios_frame.pack(fill="x", padx=5, pady=(6, 4))
    ratios_inputs = ttk.Frame(ratios_frame)
    ratios_inputs.pack(fill="x", padx=4, pady=4)
    ttk.Label(ratios_inputs, text="Min:").pack(side="left")
    ttk.Entry(ratios_inputs, textvariable=ratio_min_var, width=8).pack(side="left", padx=(2, 10))
    ttk.Label(ratios_inputs, text="Max:").pack(side="left")
    ttk.Entry(ratios_inputs, textvariable=ratio_max_var, width=8).pack(side="left", padx=2)

    tol_frame = ttk.LabelFrame(analisis_frame, text="Tolerancia híbrida (±monto)")
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
    ttk.Label(tol_inputs, text="modo:").grid(row=1, column=2, sticky="w")
    modo_combo = ttk.Combobox(
        tol_inputs,
        textvariable=modo_tol_var,
        values=["hybrid", "ratio"],
        state="readonly",
        width=8,
    )
    modo_combo.grid(row=1, column=3, padx=(2, 10), sticky="ew")
    modo_combo.set("hybrid")

    ttk.Checkbutton(
        analisis_frame,
        text="Ejecutar adicional en modo opuesto (ratio/hybrid)",
        variable=run_ratio_var,
    ).pack(fill="x", padx=5, pady=(0, 4))

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

                df_bonos = cargar_tabla_opcional(ruta_bonus) if ruta_bonus else pd.DataFrame()
                if df_bonos is None:
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

                import importlib
                try:
                    import motor_multi_cuenta as mmc
                except Exception:
                    from motor import motor_multi_cuenta as mmc

                mmc = importlib.reload(mmc)
                print(f"[DEBUG] motor_multi_cuenta cargado desde: {getattr(mmc, '__file__', 'N/A')}")

                df_base = mmc.preparar_tabla_base_multicuenta(df_base)

                try:
                    ratio_min = float(ratio_min_var.get().strip() or 0.03)
                except Exception:
                    ratio_min = 0.03
                try:
                    ratio_max = float(ratio_max_var.get().strip() or 0.05)
                except Exception:
                    ratio_max = 0.05
                if ratio_min > ratio_max:
                    ratio_min, ratio_max = ratio_max, ratio_min

                try:
                    tol_abs = float(tol_abs_var.get().strip() or 5.0)
                except Exception:
                    tol_abs = 5.0
                try:
                    k_val = float(k_var.get().strip() or 0.004)
                except Exception:
                    k_val = 0.004

                tol_max_raw = tol_max_var.get().strip()
                if tol_max_raw:
                    try:
                        tol_max = float(tol_max_raw)
                    except Exception:
                        tol_max = None
                else:
                    tol_max = None

                modo = (modo_tol_var.get().strip() or "hybrid").lower()
                if modo not in ("hybrid", "ratio"):
                    modo = "hybrid"

                log.insert(tk.END, f"Modo principal: {modo}\n")
                modo_extra = "ratio" if modo != "ratio" else "hybrid"
                run_extra = run_ratio_var.get()
                if run_extra:
                    log.insert(tk.END, f"Se ejecutara un analisis adicional en modo {modo_extra}.\n")

                df_multi, df_self = mmc.ejecutar_motor_multicuenta(
                    df_base,
                    tolerancia_cobertura=0.10,
                    min_total_apostado=0.0,
                    max_apuestas_por_seleccion=20,
                    ratio_min_margen=ratio_min,
                    ratio_max_margen=ratio_max,
                    tol_abs=tol_abs,
                    k=k_val,
                    tol_max=tol_max,
                    modo_tolerancia=modo,
                    progress_callback=cb,
                )

                if df_multi is not None and not df_multi.empty:
                    log.insert(tk.END, f"Multiusuario ({modo}): {len(df_multi)} casos.\n")
                else:
                    log.insert(tk.END, f"Multiusuario ({modo}): sin coincidencias.\n")

                if df_self is not None and not df_self.empty:
                    log.insert(tk.END, f"Self-Hedging ({modo}): {len(df_self)} casos.\n")
                else:
                    log.insert(tk.END, f"Self-Hedging ({modo}): sin casos.\n")

                resultados = [
                    "- reports/multi_cuenta_resultado.xlsx",
                    "- reports/selfhedging_resultado.xlsx",
                    f"- Guardado en Data Dashboard: {DASHBOARD_DATA_DIR / 'reporte_riesgo_multicuenta.json'}",
                ]

                if run_extra:
                    ruta_multi_extra = REPORTS_DIR / f"multi_cuenta_resultado_{modo_extra}.xlsx"
                    ruta_self_extra = REPORTS_DIR / f"selfhedging_resultado_{modo_extra}.xlsx"
                    df_multi_extra, df_self_extra = mmc.ejecutar_motor_multicuenta(
                        df_base,
                        tolerancia_cobertura=0.10,
                        min_total_apostado=0.0,
                        max_apuestas_por_seleccion=20,
                        ratio_min_margen=ratio_min,
                        ratio_max_margen=ratio_max,
                        tol_abs=tol_abs,
                        k=k_val,
                        tol_max=tol_max,
                        modo_tolerancia=modo_extra,
                        ruta_multi=ruta_multi_extra,
                        ruta_self=ruta_self_extra,
                        generar_reporte=False,
                        progress_callback=cb,
                    )

                    if df_multi_extra is not None and not df_multi_extra.empty:
                        log.insert(tk.END, f"Multiusuario ({modo_extra}): {len(df_multi_extra)} casos.\n")
                    else:
                        log.insert(tk.END, f"Multiusuario ({modo_extra}): sin coincidencias.\n")

                    if df_self_extra is not None and not df_self_extra.empty:
                        log.insert(tk.END, f"Self-Hedging ({modo_extra}): {len(df_self_extra)} casos.\n")
                    else:
                        log.insert(tk.END, f"Self-Hedging ({modo_extra}): sin casos.\n")

                    resultados.extend([
                        f"- reports/multi_cuenta_resultado_{modo_extra}.xlsx",
                        f"- reports/selfhedging_resultado_{modo_extra}.xlsx",
                    ])

                set_progress_indeterminate()

                log.see(tk.END)
                messagebox.showinfo(
                    "Motor completado",
                    "Procesamiento finalizado.\n"
                    "Resultados:\n"
                    + "\n".join(resultados),
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

    # CAMBIO: ejecutar smoke test interno sin archivo
    def lanzar_smoke_test():
        def tarea():
            try:
                btn_smoke.state(["disabled"])
                set_progress_determinate()
                log.insert(tk.END, "Ejecutando SMOKE TEST Coberturas 1X2...\n")
                log.see(tk.END)

                def cb(fase, actual, total):
                    actualizar_progress(fase, actual, total)

                import importlib
                try:
                    import motor_multi_cuenta as mmc
                except Exception:
                    from motor import motor_multi_cuenta as mmc

                mmc = importlib.reload(mmc)
                print(f"[DEBUG] motor_multi_cuenta cargado desde: {getattr(mmc, '__file__', 'N/A')}")

                df_base = mmc.generar_smoke_df()
                df_base = mmc.preparar_tabla_base_multicuenta(df_base)

                try:
                    ratio_min = float(ratio_min_var.get().strip() or 0.03)
                except Exception:
                    ratio_min = 0.03
                try:
                    ratio_max = float(ratio_max_var.get().strip() or 0.05)
                except Exception:
                    ratio_max = 0.05
                if ratio_min > ratio_max:
                    ratio_min, ratio_max = ratio_max, ratio_min

                try:
                    tol_abs = float(tol_abs_var.get().strip() or 5.0)
                except Exception:
                    tol_abs = 5.0
                try:
                    k_val = float(k_var.get().strip() or 0.004)
                except Exception:
                    k_val = 0.004

                tol_max_raw = tol_max_var.get().strip()
                if tol_max_raw:
                    try:
                        tol_max = float(tol_max_raw)
                    except Exception:
                        tol_max = None
                else:
                    tol_max = None

                modo = (modo_tol_var.get().strip() or "hybrid").lower()
                if modo not in ("hybrid", "ratio"):
                    modo = "hybrid"

                df_multi, df_self = mmc.ejecutar_motor_multicuenta(
                    df_base,
                    tolerancia_cobertura=0.10,
                    min_total_apostado=0.0,
                    max_apuestas_por_seleccion=20,
                    ratio_min_margen=ratio_min,
                    ratio_max_margen=ratio_max,
                    tol_abs=tol_abs,
                    k=k_val,
                    tol_max=tol_max,
                    modo_tolerancia=modo,
                    progress_callback=cb,
                )

                if df_multi is not None and not df_multi.empty:
                    log.insert(tk.END, f"Multiusuario ({modo}): {len(df_multi)} casos.\n")
                else:
                    log.insert(tk.END, f"Multiusuario ({modo}): sin coincidencias.\n")

                if df_self is not None and not df_self.empty:
                    log.insert(tk.END, f"Self-Hedging ({modo}): {len(df_self)} casos.\n")
                else:
                    log.insert(tk.END, f"Self-Hedging ({modo}): sin casos.\n")

                set_progress_indeterminate()
                log.see(tk.END)
                messagebox.showinfo(
                    "Smoke test completado",
                    "SMOKE TEST finalizado.\n"
                    "Resultados:\n"
                    "- reports/multi_cuenta_resultado.xlsx\n"
                    "- reports/selfhedging_resultado.xlsx\n"
                    f"- Guardado en Data Dashboard: {DASHBOARD_DATA_DIR / 'reporte_riesgo_multicuenta.json'}",
                )
                actualizar_estado_ultimo()
            except Exception:
                set_progress_indeterminate()
                log.insert(tk.END, "ERROR\n" + traceback.format_exc())
                log.see(tk.END)
                messagebox.showerror("Error", "Ocurrio un error ejecutando el smoke test.")
            finally:
                btn_smoke.state(["!disabled"])

        threading.Thread(target=tarea, daemon=True).start()

    btn_smoke.configure(command=lanzar_smoke_test)

    def lanzar_pipeline_v0():
        if not base_rutas:
            messagebox.showwarning("Advertencia", "No hay archivo base seleccionado.")
            return

        def tarea():
            try:
                btn_pipeline_v0.state(["disabled"])
                set_progress_indeterminate()
                progress.start(10)
                log.insert(tk.END, "Ejecutando PIPELINE AML v0 (Bonus Abuse + Coberturas)...\n")
                log.see(tk.END)

                resumen = ejecutar_pipeline_aml_v0(
                    rutas_apuestas=base_rutas,
                    ejecutar_multi_cuenta=True,
                    ejecutar_bonus_abuse=True,
                    path_bonos=bonus_var.get().strip() or None,
                    out_dir=str(REPORTS_DIR),
                    return_summary=True,
                )

                salidas = resumen.get("salidas", {}) if isinstance(resumen, dict) else {}
                ruta_detalle = salidas.get("detalle", "")
                ruta_global = salidas.get("global", "")
                ruta_global_json = salidas.get("pipeline_global_json", "")
                ruta_detalle_json = salidas.get("pipeline_detalle_json", "")
                ruta_detalle_meta_json = salidas.get("pipeline_detalle_meta_json", "")
                total_detecciones = int(resumen.get("total_detecciones", 0)) if isinstance(resumen, dict) else 0
                total_usuarios = int(resumen.get("total_usuarios", 0)) if isinstance(resumen, dict) else 0

                log.insert(
                    tk.END,
                    "PIPELINE AML v0 finalizado.\n"
                    f"- total_detecciones: {total_detecciones}\n"
                    f"- total_usuarios: {total_usuarios}\n"
                    f"- detalle: {ruta_detalle}\n"
                    f"- global: {ruta_global}\n"
                    f"- global_json (Data Dashboard): {ruta_global_json}\n"
                    + (
                        f"- detalle_json (Data Dashboard): {ruta_detalle_json}\n"
                        if ruta_detalle_json
                        else ""
                    )
                    + (
                        f"- detalle_meta_json (Data Dashboard): {ruta_detalle_meta_json}\n"
                        if ruta_detalle_meta_json
                        else ""
                    ),
                )
                log.see(tk.END)

                messagebox.showinfo(
                    "PIPELINE AML v0 finalizado",
                    "Procesamiento finalizado.\n"
                    f"Total detecciones: {total_detecciones}\n"
                    f"Total usuarios: {total_usuarios}\n"
                    "Salidas:\n"
                    f"- Detalle: {ruta_detalle}\n"
                    f"- Global: {ruta_global}\n"
                    f"- Global JSON: {ruta_global_json}\n"
                    + (f"- Detalle JSON: {ruta_detalle_json}\n" if ruta_detalle_json else "")
                    + (f"- Detalle META JSON: {ruta_detalle_meta_json}" if ruta_detalle_meta_json else ""),
                )
                actualizar_estado_ultimo()
            except Exception:
                log.insert(tk.END, "ERROR\n" + traceback.format_exc())
                log.see(tk.END)
                messagebox.showerror("Error", "Ocurrio un error ejecutando PIPELINE AML v0.")
            finally:
                progress.stop()
                set_progress_indeterminate()
                toggle_btn_multi_state()

        threading.Thread(target=tarea, daemon=True).start()

    btn_pipeline_v0.configure(command=lanzar_pipeline_v0)

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
                    f"- Guardado en Data Dashboard: {resumen['salidas'].get('aml_pipeline_json')}\n"
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
                    f"- Guardado en Data Dashboard: {resumen['salidas'].get('aml_pipeline_json')}",
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
