# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import inspect
from pathlib import Path

def _add_to_syspath(p: Path):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

_add_to_syspath(ROOT)
if SRC.exists():
    _add_to_syspath(SRC)
    _add_to_syspath(SRC / "motor")

def _import_pipeline():
    try:
        from motor.motor_aml_pipeline_v0 import ejecutar_pipeline_aml_v0
        return ejecutar_pipeline_aml_v0
    except Exception:
        pass

    from src.motor.motor_aml_pipeline_v0 import ejecutar_pipeline_aml_v0
    return ejecutar_pipeline_aml_v0

def _get_ruta_apuestas():
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        return sys.argv[1].strip().strip('"')
    return input("Ruta del archivo de apuestas (CSV/XLSX): ").strip().strip('"')

def main():
    ejecutar_pipeline_aml_v0 = _import_pipeline()
    ruta_apuestas = _get_ruta_apuestas()
    if not ruta_apuestas:
        print("[ERROR] No se proporciono ruta de apuestas.")
        raise SystemExit(1)

    sig = inspect.signature(ejecutar_pipeline_aml_v0)
    kwargs = {"rutas_apuestas": ruta_apuestas}

    if "ejecutar_multi_cuenta" in sig.parameters:
        kwargs["ejecutar_multi_cuenta"] = True
    if "ejecutar_bonus_abuse" in sig.parameters:
        kwargs["ejecutar_bonus_abuse"] = True
    if "path_bonos" in sig.parameters and len(sys.argv) >= 3 and sys.argv[2].strip():
        kwargs["path_bonos"] = sys.argv[2].strip().strip('"')

    print("\n[RUN] Ejecutando pipeline con:")
    for k, v in kwargs.items():
        print(f" - {k}: {v}")

    df_global = ejecutar_pipeline_aml_v0(**kwargs)

    print("\n[OK] Resultado global (top 10):")
    print(df_global.head(10).to_string(index=False))

if __name__ == "__main__":
    main()