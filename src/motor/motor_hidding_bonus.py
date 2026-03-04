import pandas as pd
from pathlib import Path
from typing import List, Tuple, Optional, Callable
import re
import unicodedata

# Tipo de callback de progreso: (fase, actual, total)
ProgressCallback = Optional[Callable[[str, int, int], None]]

# NUEVO: imports para el reporte JSON
import json
from datetime import datetime
import socket
import os

try:
    from utils.paths_dashboard import PROJECT_ROOT, REPORTS_DIR, DASHBOARD_DATA_DIR
except Exception:
    try:
        from src.utils.paths_dashboard import PROJECT_ROOT, REPORTS_DIR, DASHBOARD_DATA_DIR
    except Exception:
        PROJECT_ROOT = Path(__file__).resolve().parents[2]
        REPORTS_DIR = PROJECT_ROOT / "reports"
        DASHBOARD_DATA_DIR = PROJECT_ROOT / "Data Dashboard"
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# Utilidades internas
# ============================================================


def _normalizar_nombre_columna(nombre: str) -> str:
    s = str(nombre)
    s = s.replace("\ufeff", "").replace("ï»¿", "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def normalize_text(valor) -> str:
    s = "" if valor is None else str(valor)
    s = s.strip().lower()
    if "Ã" in s:
        try:
            s = s.encode("latin1").decode("utf-8")
        except Exception:
            pass
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9\\s]", " ", s)
    s = re.sub(r"\\s+", " ", s).strip()
    return s


def _get_col(
    df: pd.DataFrame,
    posibles: List[str],
    obligatorio: bool = True,
    nombre_logico: str = "",
) -> Optional[str]:
    """
    Devuelve el nombre de columna existente en df que coincida con alguna
    de las opciones dadas, ignorando diferencias de mayúsculas, acentos,
    guiones, espacios y caracteres no alfanuméricos. Soporta encabezados
    con BOM y variaciones leves del nombre.
    """

    cols_norm = {_normalizar_nombre_columna(c): c for c in df.columns}
    original_to_norm = {c: _normalizar_nombre_columna(c) for c in df.columns}

    for nombre in posibles:
        clave = _normalizar_nombre_columna(nombre)
        if clave in cols_norm:
            return cols_norm[clave]

    for nombre in posibles:
        norm_pos = _normalizar_nombre_columna(nombre)
        candidatos = [
            original
            for norm_col, original in cols_norm.items()
            if norm_pos in norm_col or norm_col in norm_pos
        ]
        if len(candidatos) == 1:
            return candidatos[0]
        if len(candidatos) > 1:
            return sorted(candidatos, key=len)[0]

    for nombre in posibles:
        clave = _normalizar_nombre_columna(nombre)
        for c in df.columns:
            if clave == _normalizar_nombre_columna(c):
                return c

    if not obligatorio:
        return None

    print(f"[_get_col DEBUG] posibles = {posibles}")
    print(f"[_get_col DEBUG] columnas originales = {df.columns.tolist()}")
    print(f"[_get_col DEBUG] columnas normalizadas = {original_to_norm}")
    referencia = f" para '{nombre_logico}'" if nombre_logico else ""
    raise KeyError(
        f"No se encontró ninguna columna compatible{referencia}. Posibles alias: {posibles}"
    )


def _split_teams(event_name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Intenta separar equipos local/visitante a partir del nombre del evento.
    Ejemplos:
      - "Mexico vs Cameroon"
      - "Argentina - Germany"
      - "Brazil v Spain"
    """
    if not isinstance(event_name, str):
        return None, None

    text = event_name.strip()
    for sep in [" vs ", " VS ", " - ", " v ", " V "]:
        if sep in text:
            parts = text.split(sep)
            if len(parts) == 2:
                home = parts[0].strip()
                away = parts[1].strip()
                return home, away
    return None, None


def _infer_selection_1x2(row: pd.Series, col_market: str, col_event: str) -> Optional[str]:
    """
    Intenta inferir si la apuesta es 1 / X / 2 a partir del texto del mercado
    y el nombre del evento.

    Soporta:
      - 1x2:Home, 1x2:Draw, 1x2:Away
      - mercados que contengan el nombre del equipo local o visitante
      - sufijos :1, :2, :X
    """
    market = str(row[col_market]).lower()
    event = str(row[col_event])

    # 1) Empate explícito
    if "draw" in market or "empate" in market:
        return "X"

    # 2) Patrones tipo 1x2:Home / 1x2:Away
    if "1x2" in market:
        if "home" in market:
            return "1"
        if "away" in market:
            return "2"

    # 3) Equipo local / visitante a partir del nombre de evento
    home, away = _split_teams(event)
    if home and home.lower() in market:
        return "1"
    if away and away.lower() in market:
        return "2"

    # 4) Patrones genéricos por sufijo (:1, :2, :x)
    if market.endswith(":1"):
        return "1"
    if market.endswith(":2"):
        return "2"
    if market.endswith(":x"):
        return "X"

    return None


# ============================================================
# Preparación de la tabla base (filtros + columnas estándar)
# ============================================================

def preparar_tabla_base_hidding_bonus(df_apuestas: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica los filtros necesarios y construye la tabla base para análisis
    de HiddingBonus / self-hedging, con columnas estandarizadas:

      - user_id
      - event_name
      - sport
      - market
      - selection_inferida
      - apuesta_general
      - posible_ganancia

    y mantiene columnas originales para posible uso posterior.
    """

    df = df_apuestas.copy()

    # --- Identificación de columnas clave ---
    col_user = _get_col(
        df,
        [
            "Player Id",
            "playerid",
            "userid",
            "user_id",
            "player_id",
            "user",
            "usuario",
        ],
        nombre_logico="user_id",
    )
    col_sport = _get_col(
        df,
        ["Sport", "Deporte", "sports", "tipo deporte"],
        nombre_logico="sport",
    )
    try:
        col_bet_type = _get_col(
            df,
            ["Bet type", "bettype", "bet_type", "BetType", "betType", "tipo apuesta"],
            nombre_logico="bet_type",
        )
    except KeyError:
        col_bet_type = None
        print(
            "[Filtro apuesta simple] No se encontraron columnas de tipo de apuesta "
            "(['Bet type', 'bettype']). Se omitirá este filtro."
        )
    col_status = _get_col(
        df,
        ["Status", "Estado", "bet status"],
        nombre_logico="status",
    )
    col_market = _get_col(
        df,
        ["Market types", "Market type", "Tipo mercado", "market", "market 1x2"],
        nombre_logico="market",
    )
    col_event = _get_col(
        df,
        ["Event name", "Evento", "Partido", "match", "event"],
        nombre_logico="event_name",
    )
    col_stake = _get_col(
        df,
        ["Stake", "Valor apostado", "Bet amount", "importe"],
        nombre_logico="stake",
    )

    # Bonus stake opcional
    try:
        col_bonus_stake = _get_col(df, ["Bonus stake", "bonusstake"])
    except KeyError:
        col_bonus_stake = None

    # Precio / cuota neta para calcular posible ganancia
    # Idealmente "Net Price", de lo contrario "Price".
    try:
        col_net_price = _get_col(
            df,
            ["Net Price", "Net price", "netprice", "price", "cuota", "odd", "odds"],
            nombre_logico="net_price",
        )
    except KeyError:
        col_net_price = None

    print("[Filtro deporte] Distintos valores de 'Sport' en la data original:",
          df[col_sport].nunique())

    # --- Filtro deporte (futbol / soccer) ---
    sport_norm = df[col_sport].map(normalize_text)
    print("[Filtro deporte] Top 10 valores unicos normalizados:",
          sport_norm.value_counts().head(10).index.tolist())

    sport_map = {
        "futbol": "soccer",
        "football": "soccer",
        "soccer": "soccer",
    }
    sport_std = sport_norm.map(lambda s: sport_map.get(s, s))
    allowed = {"soccer"}
    antes = len(df)
    df_filtrado = df[sport_std.isin(allowed)].copy()
    print(f"[Filtro deporte] Registros antes del filtro: {antes}")
    print(f"[Filtro deporte] Registros despues de filtrar futbol/soccer: {len(df_filtrado)}")

    if df_filtrado.empty:
        print("[WARNING] [Filtro deporte] El filtro dejo 0 filas. Se desactiva el filtro.")
        print("[WARNING] [Filtro deporte] Top 10 normalizados:",
              sport_norm.value_counts().head(10).index.tolist())
    else:
        df = df_filtrado

    # --- Filtro apuesta simple ---
    if col_bet_type is not None:
        bet_norm = df[col_bet_type].astype(str).str.lower()
        antes = len(df)
        df = df[bet_norm.isin(["single", "simple", "sencilla"])]
        print(f"[Filtro apuesta simple] Registros antes del filtro: {antes}")
        print(f"[Filtro apuesta simple] Registros después: {len(df)}")
    else:
        print("[Filtro apuesta simple] Filtro omitido por falta de columna Bet type/bettype.")

    # --- Filtro estado (removemos canceladas/void) ---
    status_norm = df[col_status].astype(str).str.lower()
    antes = len(df)
    df = df[~status_norm.isin(
        ["cancelled", "canceled", "void", "anulada", "rechazada", "rejected"]
    )]
    print(f"[Filtro estado] Registros antes del filtro: {antes}")
    print(f"[Filtro estado] Registros después (sin cancel/void): {len(df)}")

    # --- Filtro mercado 1X2 ---
    mkt_norm = df[col_market].astype(str).str.lower()
    antes = len(df)
    df = df[mkt_norm.str.contains("1x2")]
    print(f"[Filtro mercado 1X2] Registros antes del filtro: {antes}")
    print(f"[Filtro mercado 1X2] Registros después: {len(df)}")

    # --- Inferencia de selección 1 / X / 2 ---
    print("[Inferencia 1X2] Calculando 'selection_inferida'...")
    df["selection_inferida"] = df.apply(
        lambda r: _infer_selection_1x2(r, col_market, col_event),
        axis=1,
    )
    conteo_sel = df["selection_inferida"].value_counts(dropna=False)
    print("[Inferencia 1X2] Conteo de selection_inferida:")
    print(conteo_sel)

    antes = len(df)
    df = df[df["selection_inferida"].isin(["1", "X", "2"])].copy()
    print(f"[Inferencia 1X2] Registros antes del filtro: {antes}")
    print(f"[Inferencia 1X2] Registros después (con selección inferida válida): {len(df)}")

    # --- Cálculo de montos ---
    print("[Montos] Calculando columnas 'apuesta_general' y 'posible_ganancia'...")
    if col_bonus_stake is not None:
        df["apuesta_general"] = (
            df[col_stake].astype(float) + df[col_bonus_stake].astype(float)
        )
    else:
        df["apuesta_general"] = df[col_stake].astype(float)

    if col_net_price is not None:
        df["posible_ganancia"] = df["apuesta_general"] * df[col_net_price].astype(float)
    else:
        # Si no hay cuota, dejamos posible_ganancia igual a stake
        df["posible_ganancia"] = df["apuesta_general"]

    # --- Renombrar columnas estándar ---
    df["user_id"] = df[col_user]
    df["event_name"] = df[col_event]
    df["sport"] = df[col_sport]
    df["market"] = df[col_market]

    cols_order = [
        "user_id",
        "event_name",
        "sport",
        "market",
        "selection_inferida",
        "apuesta_general",
        "posible_ganancia",
    ]
    otros = [c for c in df.columns if c not in cols_order]
    df = df[cols_order + otros]

    return df


# ============================================================
# Detector multi-usuario (HiddingBonus entre usuarios)
# ============================================================

def ejecutar_hidding_bonus(
    df_apuestas: pd.DataFrame,
    tolerancia_cobertura: float = 0.10,
    min_total_apostado: float = 0.0,
    ruta_base: str | Path = REPORTS_DIR / "hidding_bonus_base.xlsx",
    ruta_multi: str | Path = REPORTS_DIR / "hidding_bonus_multiusuario.xlsx",
    max_apuestas_por_seleccion: int = 20,
    progress_callback: ProgressCallback = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Busca TRÍOS de usuarios (3 distintos) por evento que:
      - cubren 1/X/2
      - y cuya posible ganancia de cada selección está cerca del total apostado
        entre los tres (diferencia relativa máxima <= tolerancia_cobertura).

    Además asigna un nivel de riesgo multiusuario:
      - ALTO  si diff_max <= 0.05 y total_apostado alto
      - MEDIO si diff_max <= 0.10
      - BAJO  en el resto de casos que pasen el filtro

    Devuelve:
      - df_base: tabla filtrada base
      - df_trios: tabla resumen (1 fila por trío)
    """

    ruta_base = Path(ruta_base)
    ruta_multi = Path(ruta_multi)
    ruta_base.parent.mkdir(parents=True, exist_ok=True)
    ruta_multi.parent.mkdir(parents=True, exist_ok=True)

    # 1) Tabla base con filtros de deporte, bet type, estados, 1x2, etc.
    df_base = preparar_tabla_base_hidding_bonus(df_apuestas)

    # Solo 1 / X / 2 válidos
    df = df_base[df_base["selection_inferida"].isin(["1", "X", "2"])].copy()

    print("Buscando TRÍOS multiusuario con filtro de cobertura...")

    registros_resumen = []
    registros_detalle = []
    trios_vistos = set()

    # Eventos que tienen al menos una apuesta a 1, X y 2
    cobertura_por_evento = (
        df.groupby(["event_name", "selection_inferida"])["user_id"]
        .nunique()
        .unstack(fill_value=0)
    )
    eventos_con_1x2 = cobertura_por_evento[
        (cobertura_por_evento.get("1", 0) > 0)
        & (cobertura_por_evento.get("X", 0) > 0)
        & (cobertura_por_evento.get("2", 0) > 0)
    ].index.tolist()
    print(f"Eventos con al menos una apuesta 1/X/2: {len(eventos_con_1x2)}")

    df = df[df["event_name"].isin(eventos_con_1x2)]
    eventos = df.groupby("event_name")
    total_eventos = len(eventos)
    print(f"Eventos a analizar para tríos: {total_eventos}")

    # ---------- PROGRESO POR EVENTO (sin prints por conteo) ----------
    for idx, (ev_name, grp) in enumerate(eventos, start=1):
        if progress_callback is not None and total_eventos > 0:
            progress_callback("multiusuario", idx, total_eventos)

        g1 = grp[grp["selection_inferida"] == "1"]
        gX = grp[grp["selection_inferida"] == "X"]
        g2 = grp[grp["selection_inferida"] == "2"]

        if g1.empty or gX.empty or g2.empty:
            continue

        # Para evitar explosión combinatoria, recortamos al máximo indicado
        g1_small = g1.head(max_apuestas_por_seleccion)
        gX_small = gX.head(max_apuestas_por_seleccion)
        g2_small = g2.head(max_apuestas_por_seleccion)

        for _, r1 in g1_small.iterrows():
            for _, rX in gX_small.iterrows():
                for _, r2 in g2_small.iterrows():
                    u1 = str(r1["user_id"])
                    uX = str(rX["user_id"])
                    u2 = str(r2["user_id"])

                    # 3 usuarios distintos
                    if len({u1, uX, u2}) < 3:
                        continue

                    # evitar duplicados
                    clave = (ev_name, tuple(sorted([u1, uX, u2])))
                    if clave in trios_vistos:
                        continue
                    trios_vistos.add(clave)

                    # total apostado
                    stake_total = (
                        float(r1["apuesta_general"])
                        + float(rX["apuesta_general"])
                        + float(r2["apuesta_general"])
                    )
                    if stake_total <= min_total_apostado:
                        continue

                    # posibles ganancias por selección
                    g_sel = [
                        float(r1["posible_ganancia"]),
                        float(rX["posible_ganancia"]),
                        float(r2["posible_ganancia"]),
                    ]

                    # diferencia relativa de cada selección vs total apostado
                    diffs_rel = [abs(g - stake_total) / stake_total for g in g_sel]
                    diff_max = max(diffs_rel)

                    # condición de cobertura
                    if diff_max > tolerancia_cobertura:
                        continue

                    ratios = [g / stake_total for g in g_sel]
                    ratio_min = min(ratios)
                    ratio_max = max(ratios)
                    g_prom = sum(g_sel) / 3.0

                    # Nivel de riesgo multiusuario
                    if diff_max <= 0.05 and stake_total >= 50:
                        nivel_riesgo_multi = "ALTO"
                    elif diff_max <= 0.10:
                        nivel_riesgo_multi = "MEDIO"
                    else:
                        nivel_riesgo_multi = "BAJO"

                    # --------- Resumen (1 fila por trío) ---------
                    registros_resumen.append(
                        {
                            "event_name": ev_name,
                            "usuarios_implicados": f"{u1} | {uX} | {u2}",
                            "cantidad_usuarios": 3,
                            "total_apostado": stake_total,
                            "posible_ganancia_promedio": g_prom,
                            "posible_ganancia_min": min(g_sel),
                            "posible_ganancia_max": max(g_sel),
                            "ratio_min": ratio_min,
                            "ratio_max": ratio_max,
                            "dif_rel_max_vs_total": diff_max,
                            "selecciones_por_usuario": (
                                f"{u1}:1 | {uX}:X | {u2}:2"
                            ),
                            "nivel_riesgo_multi": nivel_riesgo_multi,
                        }
                    )

                    # --------- Detalle (3 filas por trío) ---------
                    registros_detalle.append(
                        {
                            "event_name": ev_name,
                            "user_id": u1,
                            "selection": "1",
                            "apuesta_general": r1["apuesta_general"],
                            "posible_ganancia": r1["posible_ganancia"],
                        }
                    )
                    registros_detalle.append(
                        {
                            "event_name": ev_name,
                            "user_id": uX,
                            "selection": "X",
                            "apuesta_general": rX["apuesta_general"],
                            "posible_ganancia": rX["posible_ganancia"],
                        }
                    )
                    registros_detalle.append(
                        {
                            "event_name": ev_name,
                            "user_id": u2,
                            "selection": "2",
                            "apuesta_general": r2["apuesta_general"],
                            "posible_ganancia": r2["posible_ganancia"],
                        }
                    )

    df_trios = pd.DataFrame(registros_resumen)
    df_trios_detalle = pd.DataFrame(registros_detalle)

    # Guardar tabla base en Excel
    df_base.to_excel(ruta_base, index=False)
    print(f"Tabla base guardada en: {ruta_base}")

    if not df_trios.empty:
        df_trios.to_excel(ruta_multi, index=False)
        print(f"Tríos multi-usuario (resumen) guardados en: {ruta_multi}")
        print(f"Total tríos detectados (tras filtro de cobertura): {len(df_trios)}")

        if not df_trios_detalle.empty:
            ruta_detalle_trios = REPORTS_DIR / "hidding_bonus_multiusuario_trios_detalle.xlsx"
            ruta_detalle_trios.parent.mkdir(parents=True, exist_ok=True)
            df_trios_detalle.to_excel(ruta_detalle_trios, index=False)
            print(f"Detalle de tríos guardado en: {ruta_detalle_trios}")
    else:
        print("No se encontraron tríos multiusuario que cumplan el filtro de cobertura.")

    return df_base, df_trios


# ============================================================
# Detector self-hedging (mismo usuario cubre 1/X/2)
# ============================================================

def ejecutar_self_hedging(
    df_base: pd.DataFrame,
    ruta_resultados: str | Path = REPORTS_DIR / "hidding_bonus_selfhedging.xlsx",
    progress_callback: ProgressCallback = None,
) -> pd.DataFrame:
    """
    Detecta patrones de self-hedging (mismo usuario cubriendo 1/X/2 en un mismo evento)
    y devuelve un DataFrame RESUMEN con una fila por (user_id, event_name),
    en un formato similar al de los tríos multiusuario.

    Además genera un archivo de DETALLE con las 3 apuestas por caso:
      - hidding_bonus_selfhedging.xlsx              (resumen)
      - hidding_bonus_selfhedging_detalle.xlsx      (detalle)
    """

    print("\nDetectando self-hedging...")

    ruta_resultados = Path(ruta_resultados)
    ruta_resultados.parent.mkdir(parents=True, exist_ok=True)

    # Trabajamos solo con filas que tienen selección_inferida 1/X/2
    if "selection_inferida" not in df_base.columns:
        print("  ⚠ La tabla base no tiene columna 'selection_inferida'.")
        return pd.DataFrame()

    df = df_base[df_base["selection_inferida"].isin(["1", "X", "2"])].copy()
    if df.empty:
        print("  ⚠ No hay apuestas con selección 1/X/2 para analizar self-hedging.")
        return pd.DataFrame()

    # Verificamos columnas clave
    for col_necesaria in ["user_id", "event_name", "apuesta_general", "posible_ganancia"]:
        if col_necesaria not in df.columns:
            print(f"  ⚠ La tabla base no tiene la columna requerida: {col_necesaria}")
            return pd.DataFrame()

    registros_resumen = []
    registros_detalle = []

    # Agrupar por usuario+evento
    grupos = df.groupby(["user_id", "event_name"])
    total_grupos = len(grupos)
    print(f"Grupos usuario+evento a analizar (self-hedging): {total_grupos}")

    for idx, ((user_id, ev_name), grp) in enumerate(grupos, start=1):
        if progress_callback is not None and total_grupos > 0:
            progress_callback("selfhedging", idx, total_grupos)

        # Necesitamos que el mismo usuario tenga apuestas a 1, X y 2
        g1 = grp[grp["selection_inferida"] == "1"]
        gX = grp[grp["selection_inferida"] == "X"]
        g2 = grp[grp["selection_inferida"] == "2"]

        if g1.empty or gX.empty or g2.empty:
            continue

        # Tomamos UNA apuesta por selección (la primera de cada grupo)
        r1 = g1.iloc[0]
        rX = gX.iloc[0]
        r2 = g2.iloc[0]

        # Total apostado
        stake_total = (
            float(r1["apuesta_general"])
            + float(rX["apuesta_general"])
            + float(r2["apuesta_general"])
        )
        if stake_total <= 0:
            continue

        # Posibles ganancias por selección
        g_sel = [
            float(r1["posible_ganancia"]),
            float(rX["posible_ganancia"]),
            float(r2["posible_ganancia"]),
        ]

        # Ratios y diferencia relativa
        ratios = [g / stake_total for g in g_sel]
        ratio_min = min(ratios)
        ratio_max = max(ratios)

        diffs_rel = [abs(g - stake_total) / stake_total for g in g_sel]
        diff_max = max(diffs_rel)

        # Clasificación simple de riesgo según cobertura
        if diff_max <= 0.10:
            nivel_riesgo = "BAJO"
        elif diff_max <= 0.30:
            nivel_riesgo = "MEDIO"
        else:
            nivel_riesgo = "ALTO"

        g_prom = sum(g_sel) / 3.0

        # --------- RESUMEN (1 fila por user+evento) ----------
        resumen = {
            "event_name": ev_name,
            "usuarios_implicados": str(user_id),
            "cantidad_usuarios": 1,
            "total_apostado": stake_total,
            "posible_ganancia_promedio": g_prom,
            "posible_ganancia_min": min(g_sel),
            "posible_ganancia_max": max(g_sel),
            "ratio_min": ratio_min,
            "ratio_max": ratio_max,
            "dif_rel_max_vs_total": diff_max,
            "selecciones_por_usuario": f"{user_id}:1,X,2",
            "nivel_riesgo_self": nivel_riesgo,
        }
        registros_resumen.append(resumen)

        # --------- DETALLE (3 filas por caso) ----------
        registros_detalle.append(
            {
                "event_name": ev_name,
                "user_id": user_id,
                "selection": "1",
                "apuesta_general": r1["apuesta_general"],
                "posible_ganancia": r1["posible_ganancia"],
            }
        )
        registros_detalle.append(
            {
                "event_name": ev_name,
                "user_id": user_id,
                "selection": "X",
                "apuesta_general": rX["apuesta_general"],
                "posible_ganancia": rX["posible_ganancia"],
            }
        )
        registros_detalle.append(
            {
                "event_name": ev_name,
                "user_id": user_id,
                "selection": "2",
                "apuesta_general": r2["apuesta_general"],
                "posible_ganancia": r2["posible_ganancia"],
            }
        )

    df_resumen = pd.DataFrame(registros_resumen)
    df_detalle = pd.DataFrame(registros_detalle)

    # Guardar resultados en Excel
    if not df_resumen.empty:
        df_resumen.to_excel(ruta_resultados, index=False)
        print(f"Self-hedging detectado: {len(df_detalle)} apuestas (detalle).")
        print(f"Casos (user+evento) de self-hedging: {len(df_resumen)}")
        print(f"Resultados resumen guardados en: {ruta_resultados}")

        if not df_detalle.empty:
            ruta_detalle = REPORTS_DIR / "hidding_bonus_selfhedging_detalle.xlsx"
            ruta_detalle.parent.mkdir(parents=True, exist_ok=True)
            df_detalle.to_excel(
                ruta_detalle,
                index=False,
            )
            print(f"Detalle de self-hedging guardado en: {ruta_detalle}")
    else:
        print("No se detectaron patrones de self-hedging.")

    return df_resumen


# ============================================================
# NUEVO: Generador de reporte JSON para seguimiento / Gemini
# ============================================================

def _contar_niveles(df: Optional[pd.DataFrame], col_nivel: str) -> dict:
    conteo = {"ALTO": 0, "MEDIO": 0, "BAJO": 0}
    if df is None or df.empty or col_nivel not in df.columns:
        return conteo
    vc = df[col_nivel].value_counts()
    for k in ["ALTO", "MEDIO", "BAJO"]:
        if k in vc.index:
            conteo[k] = int(vc[k])
    return conteo



def actualizar_historico_riesgo(
    reporte_riesgo: dict,
    ruta_historico: str | Path = DASHBOARD_DATA_DIR / "historico_riesgo_hiddingbonus.json",
):
    import os, json
    from datetime import datetime
    ruta_historico = Path(ruta_historico)
    ruta_historico.parent.mkdir(parents=True, exist_ok=True)
    meta = reporte_riesgo.get("metadata", {})
    resumen = reporte_riesgo.get("resumen_ejecucion", {})
    est = reporte_riesgo.get("estadisticas_riesgo", {})
    fecha_iso = meta.get("fecha_ejecucion", datetime.now().isoformat(timespec="seconds"))
    fecha_dia = fecha_iso[:10]
    total_tx = resumen.get("total_transacciones", 0)
    ratio = resumen.get("ratio_sospecha_global", 0.0)
    multi = est.get("multiusuario", {}) or {}
    selfh = est.get("self_hedging", {}) or {}
    casos_multi = multi.get("casos_totales", 0) or 0
    casos_self = selfh.get("casos_totales", 0) or 0
    total_casos = casos_multi + casos_self
    entry = {
        "id_ejecucion": meta.get("id_ejecucion") or f"EXEC-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "fecha_ejecucion": fecha_dia,
        "transacciones_totales": int(total_tx),
        "total_casos_detectados": int(total_casos),
        "ratio_sospecha_global": float(ratio),
        "casos_multiusuario": int(casos_multi),
        "casos_self_hedging": int(casos_self),
    }
    if os.path.exists(ruta_historico):
        try:
            historico = json.load(open(ruta_historico, encoding="utf-8-sig"))
        except:
            historico={"ejecuciones":[]}
    else:
        historico={"ejecuciones":[]}
    historico.setdefault("ejecuciones", []).append(entry)
    json.dump(historico, open(ruta_historico,"w",encoding="utf-8-sig"), ensure_ascii=False, indent=2)

def generar_reporte_json(
    df_base: pd.DataFrame,
    df_multi: Optional[pd.DataFrame] = None,
    df_self: Optional[pd.DataFrame] = None,
    archivos_entrada: Optional[list] = None,
    total_apuestas_original: Optional[int] = None,
    tolerancia_cobertura: Optional[float] = None,
    min_total_apostado: Optional[float] = None,
    max_apuestas_por_seleccion: Optional[int] = None,
    tiempo_proceso_seg: Optional[float] = None,
    nombre_archivo: str | Path = DASHBOARD_DATA_DIR / "reporte_riesgo_hiddingbonus.json",
) -> None:
    """
    Genera un archivo JSON con el resumen de riesgo para usar, por ejemplo,
    en Gemini AI Studio o dashboards externos.

    df_base: tabla base filtrada
    df_multi: resumen de tríos multiusuario
    df_self: resumen de self-hedging
    archivos_entrada: lista de archivos de apuestas procesados
    total_apuestas_original: apuestas antes de filtros (opcional)
    """

    df_multi = df_multi if df_multi is not None else pd.DataFrame()
    df_self = df_self if df_self is not None else pd.DataFrame()
    archivos_entrada = archivos_entrada or []

    # Totales básicos
    total_base = len(df_base) if df_base is not None else 0
    total_transacciones = int(total_apuestas_original) if total_apuestas_original is not None else int(total_base)

    usuarios_analizados = 0
    eventos_analizados = 0
    if df_base is not None and not df_base.empty:
        if "user_id" in df_base.columns:
            usuarios_analizados = int(df_base["user_id"].nunique())
        if "event_name" in df_base.columns:
            eventos_analizados = int(df_base["event_name"].nunique())

    casos_multi = len(df_multi) if not df_multi.empty else 0
    casos_self = len(df_self) if not df_self.empty else 0
    casos_sospechosos_totales = casos_multi + casos_self

    if total_transacciones > 0:
        ratio_sospecha_global = casos_sospechosos_totales / total_transacciones
    else:
        ratio_sospecha_global = 0.0

    # Estadísticas por nivel
    niveles_multi = _contar_niveles(df_multi, "nivel_riesgo_multi")
    niveles_self = _contar_niveles(df_self, "nivel_riesgo_self")

    # ------------------ TOP USUARIOS ------------------
    usuarios_stats = {}

    # Multiusuario: columna usuarios_implicados con "u1 | u2 | u3"
    if not df_multi.empty and "usuarios_implicados" in df_multi.columns:
        for _, row in df_multi.iterrows():
            ev_name = row.get("event_name", "")
            usuarios_str = str(row["usuarios_implicados"])
            usuarios = [u.strip() for u in usuarios_str.split("|") if u.strip()]
            for u in usuarios:
                if u not in usuarios_stats:
                    usuarios_stats[u] = {
                        "casos_multi": 0,
                        "casos_self": 0,
                        "eventos": set(),
                    }
                usuarios_stats[u]["casos_multi"] += 1
                if ev_name:
                    usuarios_stats[u]["eventos"].add(ev_name)

    # Self-hedging: usuarios_implicados es un solo user_id
    if not df_self.empty and "usuarios_implicados" in df_self.columns:
        for _, row in df_self.iterrows():
            ev_name = row.get("event_name", "")
            u = str(row["usuarios_implicados"])
            if u not in usuarios_stats:
                usuarios_stats[u] = {
                    "casos_multi": 0,
                    "casos_self": 0,
                    "eventos": set(),
                }
            usuarios_stats[u]["casos_self"] += 1
            if ev_name:
                usuarios_stats[u]["eventos"].add(ev_name)

    top_usuarios_riesgo = []
    for u, data_u in usuarios_stats.items():
        total_casos = data_u["casos_multi"] + data_u["casos_self"]
        tipos = []
        if data_u["casos_multi"] > 0:
            tipos.append("multiusuario")
        if data_u["casos_self"] > 0:
            tipos.append("self_hedging")
        top_usuarios_riesgo.append(
            {
                "usuario_id": u,
                "casos_total": total_casos,
                "casos_multiusuario": data_u["casos_multi"],
                "casos_self_hedging": data_u["casos_self"],
                "eventos_involucrados": len(data_u["eventos"]),
                "tipos_riesgo": tipos,
            }
        )

    top_usuarios_riesgo.sort(key=lambda x: x["casos_total"], reverse=True)
    top_usuarios_riesgo = top_usuarios_riesgo[:20]

    # ------------------ TOP EVENTOS ------------------
    eventos_stats = {}

    def _agg_eventos(df_local: pd.DataFrame, fuente: str, col_nivel: str):
        if df_local.empty:
            return
        for _, row in df_local.iterrows():
            ev_name = row.get("event_name", "")
            if not ev_name:
                continue
            usuarios_str = str(row.get("usuarios_implicados", ""))
            usuarios = [u.strip() for u in usuarios_str.split("|") if u.strip()]
            if not usuarios:
                usuarios = [usuarios_str.strip()] if usuarios_str.strip() else []

            nivel = str(row.get(col_nivel, "")).upper()

            if ev_name not in eventos_stats:
                eventos_stats[ev_name] = {
                    "usuarios": set(),
                    "fuentes": set(),
                    "niveles": set(),
                }
            eventos_stats[ev_name]["fuentes"].add(fuente)
            for u in usuarios:
                if u:
                    eventos_stats[ev_name]["usuarios"].add(u)
            if nivel:
                eventos_stats[ev_name]["niveles"].add(nivel)

    _agg_eventos(df_multi, "multiusuario", "nivel_riesgo_multi")
    _agg_eventos(df_self, "self_hedging", "nivel_riesgo_self")

    def _max_riesgo(niveles: set) -> str:
        if not niveles:
            return ""
        prioridad = {"ALTO": 3, "MEDIO": 2, "BAJO": 1}
        mejor_nivel = None
        mejor_score = 0
        for n in niveles:
            score = prioridad.get(n.upper(), 0)
            if score > mejor_score:
                mejor_score = score
                mejor_nivel = n.upper()
        return mejor_nivel or ""

    top_eventos_sospechosos = []
    for ev_name, data_ev in eventos_stats.items():
        fuentes = list(sorted(data_ev["fuentes"]))
        riesgo_max = _max_riesgo(data_ev["niveles"])
        top_eventos_sospechosos.append(
            {
                "evento_id": ev_name,
                "usuarios_involucrados": len(data_ev["usuarios"]),
                "fuentes": fuentes,
                "riesgo_maximo": riesgo_max,
            }
        )

    top_eventos_sospechosos.sort(
        key=lambda x: (x["riesgo_maximo"] != "ALTO", -x["usuarios_involucrados"])
    )
    top_eventos_sospechosos = top_eventos_sospechosos[:20]

    # ------------------ Parámetros del motor ------------------
    parametros_motor = {
        "tolerancia_cobertura": tolerancia_cobertura,
        "min_total_apostado": min_total_apostado,
        "max_apuestas_por_seleccion": max_apuestas_por_seleccion,
    }

    # ------------------ Construcción del JSON ------------------
    reporte_riesgo = {
        "metadata": {
            "nombre_motor": "HiddingBonusRiskEngine",
            "version": "1.0.0",
            "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
            "servidor": socket.gethostname(),
            "archivos_procesados": list(archivos_entrada),
        },
        "resumen_ejecucion": {
            "total_transacciones": total_transacciones,
            "usuarios_analizados": usuarios_analizados,
            "eventos_analizados": eventos_analizados,
            "tiempo_proceso_seg": round(tiempo_proceso_seg, 2) if tiempo_proceso_seg is not None else None,
            "ratio_sospecha_global": round(ratio_sospecha_global, 6),
        },
        "estadisticas_riesgo": {
            "multiusuario": {
                "casos_totales": casos_multi,
                "por_nivel": niveles_multi,
            },
            "self_hedging": {
                "casos_totales": casos_self,
                "por_nivel": niveles_self,
            },
        },
        "top_usuarios_riesgo": top_usuarios_riesgo,
        "top_eventos_sospechosos": top_eventos_sospechosos,
        "parametros_motor": parametros_motor,
    }

    nombre_archivo = Path(nombre_archivo)
    nombre_archivo.parent.mkdir(parents=True, exist_ok=True)

    with open(nombre_archivo, "w", encoding="utf-8-sig") as f:
        json.dump(reporte_riesgo, f, ensure_ascii=False, indent=2)

    print("\n============================================================")
    print(f"📁 Reporte de riesgo guardado en: {nombre_archivo}")
    print("   → Este archivo se puede usar directamente en Gemini AI Studio")
    print("============================================================\n")
    # NUEVO: actualizar histórico acumulado
    try:
        actualizar_historico_riesgo(reporte_riesgo)
    except Exception as e:
        print("[ADVERTENCIA] No se pudo actualizar el histórico de riesgo:")
        print(e)

def cargar_archivo_generico(ruta: str) -> pd.DataFrame:
    """
    Carga robusta de archivos CSV/Excel con diferentes configuraciones
    de separador, decimal y codificación.
    """
    if not os.path.exists(ruta):
        raise FileNotFoundError(f"No existe el archivo: {ruta}")

    try:
        if ruta.lower().endswith(".csv"):
            try:
                return pd.read_csv(ruta, sep=",", decimal=".", encoding="utf-8-sig")
            except Exception:
                return pd.read_csv(ruta, sep=",", decimal=".", encoding="latin1")
        else:
            return pd.read_excel(ruta)
    except Exception as e:
        raise Exception(f"Error cargando archivo {ruta}: {e}")


def cruzar_con_usuarios_bonus(
    df_multi: pd.DataFrame,
    df_self: pd.DataFrame,
    ruta_bonus: str,
    columna_cruce: str = "user_id"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Cruza resultados de multiusuario y self-hedging con una base de
    usuarios que recibieron bono.
    """
    print("\n📌 Cargando base de usuarios con bonus...")
    df_bonus = cargar_archivo_generico(ruta_bonus)

    # Normalizamos la columna de usuario de la base de bonus usando los mismos criterios
    # de alias que en las apuestas. Esto permite trabajar con archivos que traigan:
    #   - user_id
    #   - userid / userId
    #   - "User Id"
    #   - "Player Id" / player_id / playerid
    try:
        col_usuario_bonus = _get_col(
            df_bonus,
            [
                "user_id",
                "userid",
                "userId",
                "User Id",
                "Player Id",
                "player_id",
                "playerid",
            ],
        )
    except KeyError:
        raise ValueError(
            "La base de bonus no contiene ninguna columna de usuario compatible. "
            "Se esperaban variantes como 'user_id', 'userid', 'Player Id', etc."
        )

    if col_usuario_bonus != columna_cruce:
        print(
            f"[Bonus] Columna de usuario detectada en base de bonus: '{col_usuario_bonus}'. "
            f"Se renombrará a '{columna_cruce}' para el cruce."
        )
        df_bonus = df_bonus.rename(columns={col_usuario_bonus: columna_cruce})

    print("🔗 Cruzando con resultados multiusuario (tríos sospechosos)...")
    df_multi_cruce = pd.merge(df_multi, df_bonus, on=columna_cruce, how="inner")

    print("🔗 Cruzando con resultados self-hedging...")
    df_self_cruce = pd.merge(df_self, df_bonus, on=columna_cruce, how="inner")

    ruta_abuso_multi = REPORTS_DIR / "abuso_bonus_multiusuario.xlsx"
    ruta_abuso_self = REPORTS_DIR / "abuso_bonus_selfhedging.xlsx"
    ruta_abuso_multi.parent.mkdir(parents=True, exist_ok=True)
    ruta_abuso_self.parent.mkdir(parents=True, exist_ok=True)

    df_multi_cruce.to_excel(ruta_abuso_multi, index=False)
    df_self_cruce.to_excel(ruta_abuso_self, index=False)

    print("\n✅ Cruce de bonus completado:")
    print(f"   → {ruta_abuso_multi}")
    print(f"   → {ruta_abuso_self}")

    return df_multi_cruce, df_self_cruce

def calcular_score_abuso_bonus(
    df_multi_bonus: pd.DataFrame,
    df_self_bonus: pd.DataFrame
) -> pd.DataFrame:
    """
    Calcula un score de abuso de bono por combinación usuario/evento.
    """
    registros: list[dict] = []

    def procesar(df: pd.DataFrame, tipo: str, base_score: int):
        for _, row in df.iterrows():
            score = 0
            bono = row.get("bonus_amount", 0) or 0
            rollover = row.get("rollover", None)
            posible = row.get("posible_ganancia", row.get("posible_ganancia_promedio", 0)) or 0
            stake = row.get("apuesta_general", row.get("total_apostado", 0)) or 0

            if bono and abs(posible - bono) / max(bono, 1) < 0.15:
                score += 30
            if bono and abs(stake - bono) / max(bono, 1) < 0.15:
                score += 20

            if rollover is not None:
                try:
                    r = float(rollover)
                    if r < 5:
                        score += 15
                    elif r < 20:
                        score += 5
                except Exception:
                    pass

            score += base_score

            if score >= 80:
                nivel = "ALTO"
            elif score >= 40:
                nivel = "MEDIO"
            else:
                nivel = "BAJO"

            registros.append(
                {
                    "user_id": row.get("user_id"),
                    "event_name": row.get("event_name"),
                    "tipo": tipo,
                    "monto_bono": bono,
                    "rollover": rollover,
                    "stake_con_bonus": stake,
                    "ganancia_estimada": posible,
                    "score_abuso": score,
                    "nivel_abuso": nivel,
                }
            )

    procesar(df_multi_bonus, "multiusuario", 40)
    procesar(df_self_bonus, "selfhedging", 50)

    return pd.DataFrame(registros)


def generar_abuso_total(
    df_multi_bonus: pd.DataFrame,
    df_self_bonus: pd.DataFrame
) -> pd.DataFrame:
    """
    Genera el dataframe consolidado de abuso de bonos y lo exporta a Excel.
    """
    df = calcular_score_abuso_bonus(df_multi_bonus, df_self_bonus)
    if not df.empty:
        ruta_abuso_total = REPORTS_DIR / "abuso_bonus_total.xlsx"
        ruta_abuso_total.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(ruta_abuso_total, index=False)
        print(f"\n✅ Generado archivo {ruta_abuso_total}")
    else:
        print("\n⚠ No se generaron registros de abuso de bonus.")
    return df


def ejecutar_motor_completo(
    df_apuestas: pd.DataFrame,
    ruta_bonus: str | None = None,
    tolerancia_cobertura: float = 0.10,
    min_total_apostado: float = 0.0,
    max_apuestas_por_seleccion: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Orquesta todo el proceso:
      - Tabla base
      - Multiusuario
      - Self-Hedging
      - Cruce con Bonus (opcional)
      - Scoring de abuso de bonos (opcional)
    """
    print("\n================= INICIANDO MOTOR COMPLETO =================\n")

    df_base = preparar_tabla_base_hidding_bonus(df_apuestas)

    df_trios, df_multi = ejecutar_hidding_bonus(
        df_base,
        tolerancia_cobertura=tolerancia_cobertura,
        min_total_apostado=min_total_apostado,
        max_apuestas_por_seleccion=max_apuestas_por_seleccion,
    )

    df_self = ejecutar_self_hedging(df_base)

    if ruta_bonus:
        df_multi_bonus, df_self_bonus = cruzar_con_usuarios_bonus(
            df_multi, df_self, ruta_bonus
        )
        generar_abuso_total(df_multi_bonus, df_self_bonus)

    print("\n🎯 Motor completado.\n")

    return df_base, df_multi, df_self
