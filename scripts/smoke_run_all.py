from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pandas as pd


def _as_user_id_set(series: pd.Series) -> set[str]:
    out = set()
    for v in series.dropna().tolist():
        s = str(v).strip()
        if s.endswith(".0") and s[:-2].isdigit():
            s = s[:-2]
        if s:
            out.add(s)
    return out


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    src_dir = root / "src"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    # Reproducible: siempre regenera las bases.
    runpy.run_path(str(root / "scripts" / "generar_data_pruebas_200.py"), run_name="__main__")

    path_apuestas = root / "tests" / "data" / "base_apuestas_pruebas_200.xlsx"
    path_bonos = root / "tests" / "data" / "base_bonos_pruebas.xlsx"
    assert path_apuestas.exists(), f"No existe {path_apuestas}"
    assert path_bonos.exists(), f"No existe {path_bonos}"

    try:
        from motor.motor_multi_cuenta import preparar_tabla_base_multicuenta, ejecutar_motor_multicuenta
        from motor.motor_aml_pipeline_v0 import ejecutar_pipeline_aml_v0
    except Exception:
        from src.motor.motor_multi_cuenta import preparar_tabla_base_multicuenta, ejecutar_motor_multicuenta
        from src.motor.motor_aml_pipeline_v0 import ejecutar_pipeline_aml_v0

    df_apuestas = pd.read_excel(path_apuestas)
    df_base = preparar_tabla_base_multicuenta(df_apuestas)
    df_multi, df_self = ejecutar_motor_multicuenta(df_base.copy())

    eventos_multi = set(df_multi.get("event_name", pd.Series(dtype=object)).astype(str).tolist())
    eventos_self = set(df_self.get("event_name", pd.Series(dtype=object)).astype(str).tolist())
    assert "MU_MATCH_001" in eventos_multi, "No aparece MU_MATCH_001 en multi_cuenta"
    assert "SH_MATCH_001" in eventos_self, "No aparece SH_MATCH_001 en self_hedging"

    resumen = ejecutar_pipeline_aml_v0(
        rutas_apuestas=[str(path_apuestas)],
        ejecutar_multi_cuenta=True,
        ejecutar_bonus_abuse=True,
        path_bonos=str(path_bonos),
        out_dir=str(root / "reports"),
        return_summary=True,
    )
    assert isinstance(resumen, dict), "El pipeline no devolvio resumen dict"
    salidas = resumen.get("salidas", {})
    path_global = Path(str(salidas.get("global", "")))
    assert path_global.exists(), f"No existe salida global: {path_global}"

    df_global = pd.read_excel(path_global)
    users_global = _as_user_id_set(df_global.get("user_id", pd.Series(dtype=object)))
    expected = {"501", "502", "503", "601", "611", "621", "9001", "9002"}
    faltantes = expected - users_global
    assert not faltantes, f"Faltan user_id en pipeline_global: {sorted(faltantes)}"

    print("SMOKE OK")


if __name__ == "__main__":
    main()
