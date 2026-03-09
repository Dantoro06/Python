# -*- coding: utf-8 -*-
# aml_utils_io.py
# ==========================================================
# Utilidades de carga tabular para AML (reutiliza la logica
# de lectura del GUI para evitar divergencias).
# ==========================================================

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Optional

import pandas as pd


def _normalizar_rutas(rutas: str | Iterable[str]) -> list[str]:
    if rutas is None:
        return []
    if isinstance(rutas, (list, tuple, set)):
        return [str(r).strip() for r in rutas if str(r).strip()]
    texto = str(rutas).strip()
    if ";" in texto:
        return [p.strip() for p in texto.split(";") if p.strip()]
    return [texto] if texto else []


def _leer_tabular(
    ruta: str | Path,
    on_csv_unacolumna: Optional[Callable[[str, list[str]], None]] = None,
    fallback_csv: bool = False,
) -> Optional[pd.DataFrame]:
    ruta = str(ruta)
    if ruta.lower().endswith(".csv"):
        try:
            df = pd.read_csv(
                ruta,
                sep=";",
                decimal=",",
                encoding="utf-8",
                low_memory=False,
            )
        except Exception:
            if fallback_csv:
                return pd.read_csv(
                    ruta,
                    sep=",",
                    decimal=".",
                    encoding="utf-8-sig",
                    low_memory=False,
                )
            raise
        if df.shape[1] == 1:
            print(f"[AML IO] CSV con una sola columna tras leer con ';': {ruta}")
            if on_csv_unacolumna is not None:
                on_csv_unacolumna(ruta, list(df.columns))
            if fallback_csv:
                df_alt = pd.read_csv(
                    ruta,
                    sep=",",
                    decimal=".",
                    encoding="utf-8-sig",
                    low_memory=False,
                )
                return df_alt
            return None
        return df
    return pd.read_excel(ruta)


def cargar_base_apuestas(
    rutas: str | Iterable[str],
    on_csv_unacolumna: Optional[Callable[[str, list[str]], None]] = None,
) -> Optional[pd.DataFrame]:
    # CAMBIO: centralizar la carga de bases (misma logica que GUI)
    rutas_norm = _normalizar_rutas(rutas)
    if not rutas_norm:
        return None
    dfs = []
    for ruta in rutas_norm:
        df = _leer_tabular(ruta, on_csv_unacolumna=on_csv_unacolumna, fallback_csv=False)
        if df is None:
            return None
        for col_num in [
            "stake",
            "bonus_stake",
            "posible_ganancia",
            "bonus_amount",
            "wallet_real",
            "wallet_bono",
        ]:
            if col_num in df.columns:
                df[col_num] = pd.to_numeric(df[col_num], errors="coerce")
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def cargar_tabla_opcional(ruta: str | Path | None) -> Optional[pd.DataFrame]:
    if not ruta:
        return None
    # CAMBIO: carga tolerante para tablas opcionales
    return _leer_tabular(ruta, on_csv_unacolumna=None, fallback_csv=True)
