import pandas as pd
from pathlib import Path
from typing import List, Tuple, Optional, Callable
import re
import unicodedata
import json
from datetime import datetime
from itertools import combinations  # CAMBIO
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

# CAMBIO (enero 2026):
# - Se añade tolerancia híbrida por monto (tol_abs / k / tol_max) para multiusuario y self-hedging.
# - Se mantienen ratios como modo alternativo y se enriquece la salida con columnas de trazabilidad.
# - Se expone configuración para reportes y JSON, preservando compatibilidad previa.
# Tipo de callback de progreso: (fase, actual, total)
ProgressCallback = Optional[Callable[[str, int, int], None]]

__version__ = "TRIADAS_V3_2025-12-30"



# ============================================================
# Utilidades internas
# ============================================================


def _normalizar_nombre_columna(nombre: str) -> str:
    s = str(nombre)
    s = s.replace("\ufeff", "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def normalizar_base(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza columnas a un esquema canonico para el motor 1X2. # CAMBIO
    """
    df = df.copy()
    cols_norm = {_normalizar_nombre_columna(c): c for c in df.columns}

    mapa = {
        "sport": ["sport", "Sport", "deporte", "Deporte"],
        "market": ["market", "Market", "mercado", "Mercado"],
        "selection": ["selection", "Selection", "seleccion", "Selección", "pick", "Pick"],
        "event_name": [
            "event_name",
            "Event",
            "event",
            "Evento",
            "evento",
            "EventName",
            "eventname",
            "match",
            "Match",
            "partido",
        ],
        "fecha_apuesta": [
            "fecha_apuesta",
            "FechaApuesta",
            "fecha",
            "Fecha",
            "bet_date",
            "BetDate",
            "placed_at",
            "created_at",
        ],
        "user_id": ["user_id", "UserId", "userid", "user id", "id_usuario", "IdUsuario"],
        "bet_id": ["bet_id", "BetId", "betid", "id_apuesta", "IdApuesta"],
        "stake": ["stake", "Stake", "monto", "Monto", "amount", "Amount", "bet_amount"],
        "bet_type": ["bet_type", "BetType", "type", "Type", "tipo", "Tipo"],
        "bet_status": ["bet_status", "BetStatus", "status", "Status", "estado", "Estado"],
    }

    for canon, variantes in mapa.items():
        if canon in df.columns:
            continue
        origen = None
        for variante in variantes:
            clave = _normalizar_nombre_columna(variante)
            if clave in cols_norm:
                origen = cols_norm[clave]
                break
        if origen is not None:
            df[canon] = df[origen]

    # Tolerancia de esquema:
    # - bet_type puede faltar (se permite inferencia por ticket_id)
    # - bet_status puede faltar (se asume "open")
    if "bet_type" not in df.columns:
        df["bet_type"] = None
    if "bet_status" not in df.columns:
        df["bet_status"] = "open"

    requeridas = [
        "user_id",
        "bet_id",
        "fecha_apuesta",
        "event_name",
        "sport",
        "market",
        "selection",
        "stake",
    ]
    faltantes = [c for c in requeridas if c not in df.columns]
    if faltantes:
        raise ValueError(
            "[normalizar_base] Faltan columnas canonicas para 1X2. "
            f"Presentes: {df.columns.tolist()} | Faltantes: {faltantes}"
        )
    return df


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
    de las opciones dadas, ignorando diferencias de mayÃºsculas, acentos,
    guiones, espacios y caracteres no alfanumÃ©ricos. Soporta encabezados
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
        f"No se encontrÃ³ ninguna columna compatible{referencia}. Posibles alias: {posibles}"
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
    """
    market = str(row[col_market]).lower()
    event = str(row[col_event])

    if "draw" in market or "empate" in market:
        return "X"

    if "1x2" in market:
        if "home" in market:
            return "1"
        if "away" in market:
            return "2"

    home, away = _split_teams(event)
    if home and home.lower() in market:
        return "1"
    if away and away.lower() in market:
        return "2"

    if market.endswith(":1"):
        return "1"
    if market.endswith(":2"):
        return "2"
    if market.endswith(":x"):
        return "X"

    return None


def _fmt_user_id(valor) -> str:
    """
    Normaliza user_id a string sin sufijos '.0' cuando viene como float.
    """
    try:
        f = float(valor)
        if f.is_integer():
            return str(int(f))
    except Exception:
        pass
    return str(valor)


def _clip_ratio_margen(g_min: float, g_max: float, stake_total: float, min_ratio: float = 0.03, max_ratio: float = 0.05) -> tuple[float, float]:
    """
    Calcula el margen (ganancia - stake) / stake y lo acota al rango [min_ratio, max_ratio]
    para que el ratio mostrado sea consistente entre Multiusuario y Self-Hedging.
    """
    if stake_total <= 0:
        return 0.0, 0.0
    margin_min = (g_min - stake_total) / stake_total
    margin_max = (g_max - stake_total) / stake_total
    ratio_min = min(max(margin_min, min_ratio), max_ratio)
    ratio_max = min(max(margin_max, min_ratio), max_ratio)
    if ratio_min > ratio_max:
        ratio_min, ratio_max = ratio_max, ratio_min
    return ratio_min, ratio_max


def _calcular_tolerancia(
    total: pd.Series | float,
    tol_abs: float = 5.0,
    k: float = 0.004,
    tol_max: float | None = None,
) -> pd.Series | float:
    """
    Calcula tolerancia híbrida por monto: max(tol_abs, k * total), opcionalmente limitada por tol_max.
    Funciona con Series o escalares para reutilizar en ambos motores. # CAMBIO
    """
    serie = total if isinstance(total, pd.Series) else pd.Series([total], dtype="float")
    tol = serie.astype(float) * float(k)
    tol = tol.where(tol > tol_abs, tol_abs)
    if tol_max is not None:
        tol = tol.clip(upper=tol_max)
    if isinstance(total, pd.Series):
        return tol
    return float(tol.iloc[0])


def _imprimir_debug_filtro(
    etiqueta: str,
    df: pd.DataFrame,
    col: str,
    normalizador: Optional[Callable[[object], str]] = None,
) -> None:
    """
    Imprime conteos y top 10 unicos normalizados para depurar filtros. # CAMBIO
    """
    if col not in df.columns:
        print(f"[{etiqueta}] Columna '{col}' no existe.")
        return
    serie = df[col]
    if normalizador is None:
        norm = serie.astype(str).str.strip().str.lower()
    else:
        norm = serie.map(normalizador)
    top10 = norm.value_counts(dropna=False).head(10).index.tolist()
    print(f"[{etiqueta}] Registros: {len(df)}")
    print(f"[{etiqueta}] Top 10 unicos normalizados: {top10}")


# ============================================================
# PreparaciÃ³n de la tabla base (filtros + columnas estÃ¡ndar)
# ============================================================

def preparar_tabla_base_multicuenta(df_apuestas: pd.DataFrame, bucket: str = "min") -> pd.DataFrame:
    """
    Aplica los filtros necesarios y construye la tabla base para el motor
    multi-cuenta / self-hedging, con columnas estandarizadas:

      - user_id
      - event_name
      - sport
      - market
      - selection_inferida
      - apuesta_general
      - posible_ganancia
    """

    # CAMBIO: normalizar columnas antes de cualquier filtro
    df = normalizar_base(df_apuestas)

    # CAMBIO: parseo de tipos
    df["user_id"] = pd.to_numeric(df["user_id"], errors="coerce").astype("Int64")
    df["stake"] = pd.to_numeric(df["stake"], errors="coerce")
    df["fecha_apuesta"] = pd.to_datetime(df["fecha_apuesta"], errors="coerce")
    for col in ["sport", "market", "selection", "bet_type", "bet_status"]:
        df[col] = df[col].astype(str).str.strip().str.lower()

    # CAMBIO: bucket temporal para coincidencias por minuto (configurable)
    if "fecha_bucket" not in df.columns:
        df["fecha_bucket"] = df["fecha_apuesta"].dt.floor(bucket)

    col_user = "user_id"
    col_sport = "sport"
    col_bet_type = "bet_type"
    col_status = "bet_status"
    col_market = "market"
    col_event = "event_name"
    col_selection = "selection"
    col_stake = "stake"

    try:
        col_bonus_stake = _get_col(df, ["Bonus stake", "bonusstake"])
    except KeyError:
        col_bonus_stake = None

    try:
        col_net_price = _get_col(
            df,
            ["Net Price", "Net price", "netprice", "price", "cuota", "odd", "odds"],
            nombre_logico="net_price",
        )
    except KeyError:
        col_net_price = None
    col_posible_ganancia = _get_col(
        df,
        ["posible_ganancia", "possible_win", "possible_gain", "ganancia_posible"],
        obligatorio=False,
        nombre_logico="posible_ganancia",
    )

    _imprimir_debug_filtro("Filtro deporte (antes)", df, col_sport, normalize_text)

    sport_norm = df[col_sport].map(normalize_text)
    sport_map = {
        "futbol": "soccer",
        "football": "soccer",
        "soccer": "soccer",
    }
    sport_std = sport_norm.map(lambda s: sport_map.get(s, s))
    allowed = {"soccer", "football", "futbol"}
    df_filtrado = df[sport_std.isin({"soccer"}) | sport_norm.isin(allowed)].copy()
    print(f"[Filtro deporte] Registros despues del filtro: {len(df_filtrado)}")
    _imprimir_debug_filtro("Filtro deporte (despues)", df_filtrado, col_sport, normalize_text)

    if df_filtrado.empty:
        print("[WARNING] [Filtro deporte] El filtro dejo 0 filas.")
        print(
            df[[col_user, col_sport, col_bet_type, col_status, col_market, col_selection, col_stake, col_event, "fecha_apuesta"]]
            .head(20)
            .to_string(index=False)
        )
    else:
        df = df_filtrado

    # CAMBIO: Filtro apuesta simple robusto con inferencia por prioridad
    usar_inferencia_ticket = False
    bet_norm = df[col_bet_type].map(normalize_text)
    valid_mask = bet_norm.notna() & (~bet_norm.isin(["", "nan", "none"]))
    _imprimir_debug_filtro("Filtro apuesta simple (antes)", df, col_bet_type, normalize_text)
    if valid_mask.any():
        patron_simple = r"simple|single"
        mask_bet = bet_norm.str.contains(patron_simple, na=False)
        df_filtrado = df[mask_bet].copy()
        print(f"[Filtro apuesta simple] Registros despues del filtro: {len(df_filtrado)}")
        _imprimir_debug_filtro("Filtro apuesta simple (despues)", df_filtrado, col_bet_type, normalize_text)
        if df_filtrado.empty:
            print("[WARNING] [Filtro apuesta simple] El filtro dejo 0 filas.")
            print(
                df[[col_user, col_sport, col_bet_type, col_status, col_market, col_selection, col_stake, col_event, "fecha_apuesta"]]
                .head(20)
                .to_string(index=False)
            )
        else:
            df = df_filtrado
    else:
        print("[Filtro apuesta simple] Columna tipo apuesta sin valores. Se omite filtro.")
        usar_inferencia_ticket = True

    if usar_inferencia_ticket:
        # CAMBIO: inferencia por ticket_id cuando no hay columna explicita util
        col_ticket_id = _get_col(
            df,
            ["ticket_id", "ticketid", "ticket", "id_ticket", "idticket"],
            obligatorio=False,
            nombre_logico="ticket_id",
        )
        if col_ticket_id is None:
            print("[Filtro apuesta simple] No se encontro columna ticket_id. Se omite inferencia.")
        else:
            col_bet_id = _get_col(
                df,
                ["bet_id", "betid", "id_bet", "idapuesta", "apuesta_id"],
                obligatorio=False,
                nombre_logico="bet_id",
            )
            if col_bet_id is not None:
                legs_por_ticket = df.groupby(col_ticket_id)[col_bet_id].transform("count")
            elif col_selection is not None:
                legs_por_ticket = df.groupby(col_ticket_id)[col_selection].transform("count")
            else:
                legs_por_ticket = df.groupby(col_ticket_id)[col_ticket_id].transform("count")

            print("[Filtro apuesta simple] Metodo utilizado: B")
            print("[Filtro apuesta simple] Distribucion legs_por_ticket (top 5):")
            print(legs_por_ticket.value_counts().head(5))
            antes = len(df)
            df_filtrado = df[legs_por_ticket == 1].copy()
            print(f"[Filtro apuesta simple] Registros antes del filtro: {antes}")
            print(f"[Filtro apuesta simple] Registros despues: {len(df_filtrado)}")
            if df_filtrado.empty:
                print("[WARNING] [Filtro apuesta simple] El filtro dejo 0 filas. Se desactiva el filtro.")
            else:
                df = df_filtrado

    _imprimir_debug_filtro("Filtro estado (antes)", df, col_status)
    status_norm = df[col_status].astype(str).str.lower()
    df_filtrado = df[~status_norm.isin(
        ["cancelled", "canceled", "void", "anulada", "rechazada", "rejected"]
    )].copy()
    print(f"[Filtro estado] Registros despues del filtro: {len(df_filtrado)}")
    _imprimir_debug_filtro("Filtro estado (despues)", df_filtrado, col_status)
    if df_filtrado.empty:
        print("[WARNING] [Filtro estado] El filtro dejo 0 filas.")
        print(
            df[[col_user, col_sport, col_bet_type, col_status, col_market, col_selection, col_stake, col_event, "fecha_apuesta"]]
            .head(20)
            .to_string(index=False)
        )
    else:
        df = df_filtrado

    _imprimir_debug_filtro("Filtro mercado 1X2 (antes)", df, col_market)
    mkt_norm = df[col_market].astype(str).str.lower()
    mkt_ok = mkt_norm.isin(
        ["1x2", "match_result", "resultado_final", "full_time_result"]
    ) | mkt_norm.str.contains("1x2", na=False)
    df_filtrado = df[mkt_ok].copy()
    print(f"[Filtro mercado 1X2] Registros despues del filtro: {len(df_filtrado)}")
    _imprimir_debug_filtro("Filtro mercado 1X2 (despues)", df_filtrado, col_market)
    if df_filtrado.empty:
        print("[WARNING] [Filtro mercado 1X2] El filtro dejo 0 filas.")
        print(
            df[[col_user, col_sport, col_bet_type, col_status, col_market, col_selection, col_stake, col_event, "fecha_apuesta"]]
            .head(20)
            .to_string(index=False)
        )
    else:
        df = df_filtrado

    print("[Inferencia 1X2] Calculando 'selection_inferida'...")
    if col_selection is not None:
        s = df[col_selection].astype(str).str.strip().str.upper()
        s = s.replace(
            {
                "DRAW": "X",
                "TIE": "X",
                "EMPATE": "X",
                "D": "X",
                "HOME": "1",
                "LOCAL": "1",
                "H": "1",
                "AWAY": "2",
                "VISITANTE": "2",
                "A": "2",
            }
        )
        last_token = s.str.extract(r"([12X])$", expand=False)
        s = s.where(s.isin(["1", "X", "2"]), last_token)
        df["selection_inferida"] = s.where(s.isin(["1", "X", "2"]), None)
    else:
        df["selection_inferida"] = df.apply(
            lambda r: _infer_selection_1x2(r, col_market, col_event),
            axis=1,
        )
    conteo_sel = df["selection_inferida"].value_counts(dropna=False)
    print("[Inferencia 1X2] Conteo de selection_inferida:")
    print(conteo_sel)

    # CAMBIO: normalizar seleccion para deteccion (X mayuscula)
    base_sel = df["selection_inferida"] if "selection_inferida" in df.columns else df[col_selection]
    sel_norm = base_sel.astype(str).str.strip().str.upper()
    sel_norm = sel_norm.replace({"DRAW": "X", "TIE": "X", "D": "X", "0": "X"})
    df["sel_norm"] = sel_norm

    _imprimir_debug_filtro("Filtro seleccion (antes)", df, "sel_norm")
    df_filtrado = df[df["sel_norm"].isin(["1", "X", "2"])].copy()
    print(f"[Filtro seleccion] Registros despues del filtro: {len(df_filtrado)}")
    _imprimir_debug_filtro("Filtro seleccion (despues)", df_filtrado, "sel_norm")
    if df_filtrado.empty:
        print("[WARNING] [Filtro seleccion] El filtro dejo 0 filas.")
        print(
            df[[col_user, col_sport, col_bet_type, col_status, col_market, col_selection, col_stake, col_event, "fecha_apuesta"]]
            .head(20)
            .to_string(index=False)
        )
    else:
        df = df_filtrado

    print("[Montos] Calculando columnas 'apuesta_general' y 'posible_ganancia'...")
    if col_bonus_stake is not None:
        df["apuesta_general"] = (
            df[col_stake].astype(float) + df[col_bonus_stake].astype(float)
        )
    else:
        df["apuesta_general"] = df[col_stake].astype(float)

    if col_net_price is not None:
        net_price_raw = df[col_net_price].astype(str).str.replace(",", ".", regex=False)
        net_price = pd.to_numeric(net_price_raw, errors="coerce")
        df["posible_ganancia"] = df["apuesta_general"] * net_price
        faltantes = df["posible_ganancia"].isna().sum()
        if faltantes:
            print(f"[Montos] Net Price con valores no numericos o vacios: {faltantes}.")
    elif col_posible_ganancia is not None:
        posible_raw = df[col_posible_ganancia].astype(str).str.replace(",", ".", regex=False)
        df["posible_ganancia"] = pd.to_numeric(posible_raw, errors="coerce")
    else:
        df["posible_ganancia"] = float("nan")
    # CAMBIO: apuesta_base para deteccion (fallback stake+bonus_stake)
    if "apuesta_general" in df.columns:
        df["apuesta_base"] = df["apuesta_general"]
    elif col_bonus_stake is not None:
        df["apuesta_base"] = df[col_stake].astype(float) + df[col_bonus_stake].astype(float)
    else:
        df["apuesta_base"] = df[col_stake].astype(float)

    df["user_id"] = df[col_user]
    df["event_name"] = df[col_event]
    df["sport"] = df[col_sport]
    df["market"] = df[col_market]

    cols_order = [
        "user_id",
        "event_name",
        "fecha_bucket",
        "sport",
        "market",
        "selection_inferida",
        "sel_norm",
        "apuesta_base",
        "apuesta_general",
        "posible_ganancia",
    ]
    # Mantener columnas conocidas primero y luego el resto, sin fallar si falta alguna
    otros = [c for c in df.columns if c not in cols_order]
    cols_final = [c for c in cols_order if c in df.columns] + otros
    df = df[cols_final]

    return df


def generar_smoke_df() -> pd.DataFrame:
    """
    Genera un dataframe de prueba en memoria para smoke test. # CAMBIO
    """
    base_time = pd.Timestamp("2024-01-01 12:00:30")
    data = [
        # Multiusuario 1/X/2
        {
            "user_id": 101,
            "bet_id": 1,
            "fecha_apuesta": base_time,
            "event_name": "Team A vs Team B",
            "sport": "soccer",
            "market": "1x2",
            "selection": "1",
            "stake": 100,
            "net_price": 3.0,
            "bet_status": "open",
            "bet_type": "single",
        },
        {
            "user_id": 102,
            "bet_id": 2,
            "fecha_apuesta": base_time,
            "event_name": "Team A vs Team B",
            "sport": "soccer",
            "market": "1x2",
            "selection": "X",
            "stake": 100,
            "net_price": 3.0,
            "bet_status": "open",
            "bet_type": "single",
        },
        {
            "user_id": 103,
            "bet_id": 3,
            "fecha_apuesta": base_time,
            "event_name": "Team A vs Team B",
            "sport": "soccer",
            "market": "1x2",
            "selection": "2",
            "stake": 100,
            "net_price": 3.0,
            "bet_status": "open",
            "bet_type": "single",
        },
        # Self-hedging 1/X/2 (requiere 3 selecciones)
        {
            "user_id": 201,
            "bet_id": 4,
            "fecha_apuesta": base_time + pd.Timedelta(seconds=10),
            "event_name": "Team C vs Team D",
            "sport": "soccer",
            "market": "1x2",
            "selection": "1",
            "stake": 50,
            "net_price": 3.0,
            "bet_status": "open",
            "bet_type": "single",
        },
        {
            "user_id": 201,
            "bet_id": 5,
            "fecha_apuesta": base_time + pd.Timedelta(seconds=20),
            "event_name": "Team C vs Team D",
            "sport": "soccer",
            "market": "1x2",
            "selection": "X",
            "stake": 50,
            "net_price": 3.0,
            "bet_status": "open",
            "bet_type": "single",
        },
        {
            "user_id": 201,
            "bet_id": 6,
            "fecha_apuesta": base_time + pd.Timedelta(seconds=30),
            "event_name": "Team C vs Team D",
            "sport": "soccer",
            "market": "1x2",
            "selection": "2",
            "stake": 50,
            "net_price": 3.0,
            "bet_status": "open",
            "bet_type": "single",
        },
    ]
    return pd.DataFrame(data)


# ============================================================
# Detector multi-usuario (trÃ­os 1/X/2)
# ============================================================

def detectar_trios_multiusuario(
    df_base: pd.DataFrame,
    tolerancia_cobertura: float = 0.10,
    min_total_apostado: float = 0.0,
    max_apuestas_por_seleccion: int = 20,
    ratio_min_margen: float = 0.03,
    ratio_max_margen: float = 0.05,
    tol_abs: float = 5.0,
    k: float = 0.004,
    tol_max: float | None = None,
    modo_tolerancia: str = "hybrid",
    ruta_resultado: str | Path | None = REPORTS_DIR / "multi_cuenta_resultado.xlsx",  # CAMBIO
    progress_callback: ProgressCallback = None,
) -> pd.DataFrame:
    """
    Busca trios de usuarios por evento que cubren 1/X/2 con diferencias
    de monto dentro de la tolerancia indicada.
    """

    df = df_base.copy()
    # CAMBIO: normalizar seleccion para deteccion (X mayuscula)
    if "sel_norm" not in df.columns:
        base_sel = df["selection_inferida"] if "selection_inferida" in df.columns else df["selection"]
        sel_norm = base_sel.astype(str).str.strip().str.upper()
        sel_norm = sel_norm.replace({"DRAW": "X", "TIE": "X", "D": "X", "0": "X"})
        df["sel_norm"] = sel_norm
    df = df[df["sel_norm"].isin(["1", "X", "2"])].copy()
    # CAMBIO: asegurar bucket temporal para agrupaciones
    if "fecha_bucket" not in df.columns:
        df["fecha_bucket"] = pd.to_datetime(df.get("fecha_apuesta"), errors="coerce").dt.floor("min")

    registros_resumen = []
    trios_vistos = set()

    cobertura_por_evento = (
        df.groupby(["event_name", "fecha_bucket", "sel_norm"])["user_id"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=["1", "X", "2"], fill_value=0)
    )
    eventos_con_1x2 = cobertura_por_evento[
        (cobertura_por_evento["1"] > 0)
        & (cobertura_por_evento["X"] > 0)
        & (cobertura_por_evento["2"] > 0)
    ].index.tolist()

    if not eventos_con_1x2:
        print("[DEBUG] [Multiusuario] No hay eventos con 1/X/2 en el mismo bucket.")
        try:
            print(cobertura_por_evento.head(10))
        except Exception:
            pass

    df = df[df.set_index(["event_name", "fecha_bucket"]).index.isin(eventos_con_1x2)]
    eventos = df.groupby(["event_name", "fecha_bucket"])
    total_eventos = len(eventos)
    debug_triada_ok = False
    debug_falta_sel = False
    debug_max_diff = False
    debug_total_zero = False

    for idx, ((ev_name, fecha_bucket), grp) in enumerate(eventos, start=1):
        if progress_callback is not None and total_eventos > 0:
            progress_callback("multiusuario", idx, total_eventos)

        g1 = grp[grp["sel_norm"] == "1"]
        gX = grp[grp["sel_norm"] == "X"]
        g2 = grp[grp["sel_norm"] == "2"]

        if g1.empty or gX.empty or g2.empty:
            if not debug_falta_sel:
                print("[DEBUG] [Multiusuario] DESCARTE faltan selecciones ev/bucket:", ev_name, fecha_bucket)
                debug_falta_sel = True
            continue

        g1_u = g1.groupby("user_id")["apuesta_base"].sum().sort_values(ascending=False)
        gX_u = gX.groupby("user_id")["apuesta_base"].sum().sort_values(ascending=False)
        g2_u = g2.groupby("user_id")["apuesta_base"].sum().sort_values(ascending=False)

        g1_u_top = g1_u.head(max_apuestas_por_seleccion)
        gX_u_top = gX_u.head(max_apuestas_por_seleccion)
        g2_u_top = g2_u.head(max_apuestas_por_seleccion)

        total_sum = float(g1_u_top.sum() + gX_u_top.sum() + g2_u_top.sum())
        if total_sum <= 0:
            if not debug_total_zero:
                print("[DEBUG] [Multiusuario] DESCARTE total=0 ev/bucket:", ev_name, fecha_bucket)
                debug_total_zero = True
            continue

        g1_pg = None
        gX_pg = None
        g2_pg = None
        if "posible_ganancia" in grp.columns and grp["posible_ganancia"].notna().any():
            g1_pg = g1.groupby("user_id")["posible_ganancia"].sum(min_count=1)
            gX_pg = gX.groupby("user_id")["posible_ganancia"].sum(min_count=1)
            g2_pg = g2.groupby("user_id")["posible_ganancia"].sum(min_count=1)

        mejor = None
        had_max_diff = False

        for u1, s1 in g1_u_top.items():
            s1 = float(s1)
            if s1 <= 0:
                continue
            for uX, sX in gX_u_top.items():
                if uX == u1:
                    continue
                sX = float(sX)
                if sX <= 0:
                    continue
                for u2, s2 in g2_u_top.items():
                    if u2 == u1 or u2 == uX:
                        continue
                    s2 = float(s2)
                    if s2 <= 0:
                        continue

                    total = s1 + sX + s2
                    if total <= 0:
                        if not debug_total_zero:
                            print("[DEBUG] [Multiusuario] DESCARTE total=0 ev/bucket:", ev_name, fecha_bucket)
                            debug_total_zero = True
                        continue

                    max_diff = max(abs(s1 - sX), abs(s1 - s2), abs(sX - s2))

                    if modo_tolerancia == "ratio":
                        tol_val = total * float(ratio_max_margen)
                        if max_diff > tol_val:
                            had_max_diff = True
                            continue
                        ratio_min_val = float(ratio_min_margen)
                        ratio_max_val = float(ratio_max_margen)
                        tol_aplicada = float("nan")
                    else:
                        tol_val = _calcular_tolerancia(total, tol_abs=tol_abs, k=k, tol_max=tol_max)
                        if max_diff > tol_val:
                            had_max_diff = True
                            continue
                        ratio_eff = (tol_val / total) if total else 0.0
                        ratio_min_val = ratio_eff
                        ratio_max_val = ratio_eff
                        tol_aplicada = tol_val

                    u1_fmt = _fmt_user_id(u1)
                    uX_fmt = _fmt_user_id(uX)
                    u2_fmt = _fmt_user_id(u2)
                    clave = (ev_name, fecha_bucket, tuple(sorted([u1_fmt, uX_fmt, u2_fmt])))
                    if clave in trios_vistos:
                        continue

                    g_prom = float("nan")
                    g_min = float("nan")
                    g_max = float("nan")
                    if g1_pg is not None and gX_pg is not None and g2_pg is not None:
                        g1_val = float(g1_pg.get(u1, float("nan")))
                        gX_val = float(gX_pg.get(uX, float("nan")))
                        g2_val = float(g2_pg.get(u2, float("nan")))
                        if not (pd.isna(g1_val) or pd.isna(gX_val) or pd.isna(g2_val)):
                            g_vals = [g1_val, gX_val, g2_val]
                            g_prom = sum(g_vals) / 3.0
                            g_min = min(g_vals)
                            g_max = max(g_vals)

                    dif_rel = (max_diff / total) if total else 0.0

                    if dif_rel <= 0.05 and total >= 50:
                        nivel_riesgo = "ALTO"
                    elif dif_rel <= 0.10 and total >= 20:
                        nivel_riesgo = "MEDIO"
                    else:
                        nivel_riesgo = "BAJO"

                    candidato = {
                        "u1": u1_fmt,
                        "uX": uX_fmt,
                        "u2": u2_fmt,
                        "s1": s1,
                        "sX": sX,
                        "s2": s2,
                        "total": total,
                        "max_diff": float(max_diff),
                        "dif_rel": float(dif_rel),
                        "ratio_min": ratio_min_val,
                        "ratio_max": ratio_max_val,
                        "tol_aplicada": tol_aplicada,
                        "g_prom": g_prom,
                        "g_min": g_min,
                        "g_max": g_max,
                        "nivel_riesgo": nivel_riesgo,
                        "clave": clave,
                    }

                    if mejor is None or candidato["max_diff"] < mejor["max_diff"] or (
                        candidato["max_diff"] == mejor["max_diff"] and candidato["total"] > mejor["total"]
                    ):
                        mejor = candidato

        if mejor is None:
            if had_max_diff and not debug_max_diff:
                print("[DEBUG] [Multiusuario] DESCARTE max_diff>tol ev/bucket:", ev_name, fecha_bucket)
                debug_max_diff = True
            continue

        trios_vistos.add(mejor["clave"])

        if not debug_triada_ok:
            tol_print = mejor["tol_aplicada"] if modo_tolerancia == "hybrid" else mejor["total"] * float(ratio_max_margen)
            print(
                "[DEBUG] [Multiusuario] TRIADA OK ev/bucket",
                ev_name,
                fecha_bucket,
                "|",
                f"{mejor['u1']}/{mejor['uX']}/{mejor['u2']}",
                "|",
                f"{round(mejor['s1'], 2)}/{round(mejor['sX'], 2)}/{round(mejor['s2'], 2)}",
                "| total",
                round(mejor["total"], 2),
                "| tol",
                round(float(tol_print), 2),
                "| max_diff",
                round(float(mejor["max_diff"]), 2),
                "| modo_tolerancia",
                modo_tolerancia,
            )
            debug_triada_ok = True

        total_apostado_r = round(mejor["total"], 2)
        tol_aplicada_r = round(float(mejor["tol_aplicada"]), 2) if modo_tolerancia == "hybrid" else float("nan")
        tol_max_r = round(tol_max, 2) if tol_max is not None else float("nan")
        dif_rel_r = round(mejor["dif_rel"], 2)

        registros_resumen.append(
            {
                "event_name": ev_name,
                "fecha_bucket": fecha_bucket,
                "usuarios_implicados": f"{mejor['u1']}|{mejor['uX']}|{mejor['u2']}",
                "cantidad_usuarios": 3,
                "total_apostado": total_apostado_r,
                "posible_ganancia_promedio": round(mejor["g_prom"], 2) if mejor["g_prom"] == mejor["g_prom"] else float("nan"),
                "posible_ganancia_min": round(mejor["g_min"], 2) if mejor["g_min"] == mejor["g_min"] else float("nan"),
                "posible_ganancia_max": round(mejor["g_max"], 2) if mejor["g_max"] == mejor["g_max"] else float("nan"),
                "ratio_min": round(mejor["ratio_min"], 4),
                "ratio_max": round(mejor["ratio_max"], 4),
                "dif_rel_max_vs_total": dif_rel_r,
                "selecciones_por_usuario": f"{mejor['u1']}:1 | {mejor['uX']}:X | {mejor['u2']}:2",
                "nivel_riesgo": mejor["nivel_riesgo"],
                "tol_aplicada": tol_aplicada_r,
                "tol_abs_usada": float(tol_abs),
                "k_usado": float(k),
                "tol_max_usada": tol_max_r,
            }
        )

    df_trios = pd.DataFrame(registros_resumen)

    # Asegurar contrato: cada fila debe ser un trio (3 usuarios)
    if not df_trios.empty and "cantidad_usuarios" in df_trios.columns:
        bad = df_trios[df_trios["cantidad_usuarios"] != 3]
        if not bad.empty:
            raise ValueError(
                "[Multiusuario] Salida invalida: se detectaron filas con cantidad_usuarios != 3. "
                "Esto indica que se esta generando un resumen por evento en vez de triadas 1/X/2."
            )

    columnas_orden = [
        "event_name",
        "fecha_bucket",
        "usuarios_implicados",
        "cantidad_usuarios",
        "total_apostado",
        "posible_ganancia_promedio",
        "posible_ganancia_min",
        "posible_ganancia_max",
        "ratio_min",
        "ratio_max",
        "tol_aplicada",
        "tol_abs_usada",
        "k_usado",
        "tol_max_usada",
        "dif_rel_max_vs_total",
        "selecciones_por_usuario",
        "nivel_riesgo",
    ]

    if not df_trios.empty:
        df_trios = df_trios[df_trios["cantidad_usuarios"] == 3].copy()
        df_trios = df_trios[columnas_orden]
        numeric_cols = [
            "total_apostado",
            "posible_ganancia_promedio",
            "posible_ganancia_min",
            "posible_ganancia_max",
            "ratio_min",
            "ratio_max",
            "tol_aplicada",
            "tol_abs_usada",
            "k_usado",
            "tol_max_usada",
            "dif_rel_max_vs_total",
        ]
        for col in numeric_cols:
            df_trios[col] = df_trios[col].astype(float).round(2)
    else:
        df_trios = pd.DataFrame(columns=columnas_orden)
        print("[Info] No se detectaron trios multiusuario.")
        # CAMBIO: debug de top montos por seleccion
        if not df.empty:
            try:
                ejemplo = df.groupby(["event_name", "fecha_bucket"]).head(1)
                if not ejemplo.empty:
                    ev_name = ejemplo.iloc[0]["event_name"]
                    fb = ejemplo.iloc[0]["fecha_bucket"]
                    grp = df[(df["event_name"] == ev_name) & (df["fecha_bucket"] == fb)]
                    g1_u_dbg = grp[grp["sel_norm"] == "1"].groupby("user_id")["apuesta_base"].sum().sort_values(ascending=False).head(3)
                    gX_u_dbg = grp[grp["sel_norm"] == "X"].groupby("user_id")["apuesta_base"].sum().sort_values(ascending=False).head(3)
                    g2_u_dbg = grp[grp["sel_norm"] == "2"].groupby("user_id")["apuesta_base"].sum().sort_values(ascending=False).head(3)
                    print("[DEBUG] [Multiusuario] Ejemplo top montos ev/bucket:", ev_name, fb)
                    print("[DEBUG] [Multiusuario] Top 1:", list(g1_u_dbg.items()))
                    print("[DEBUG] [Multiusuario] Top X:", list(gX_u_dbg.items()))
                    print("[DEBUG] [Multiusuario] Top 2:", list(g2_u_dbg.items()))
            except Exception:
                pass

    # CAMBIO: permitir ejecucion sin escribir Excel cuando ruta_resultado es None
    if ruta_resultado is not None:
        ruta_resultado = Path(ruta_resultado)
        ruta_resultado.parent.mkdir(parents=True, exist_ok=True)
        try:
            df_trios.to_excel(ruta_resultado, index=False)
            print(f"[Excel] Resultado multiusuario guardado en: {ruta_resultado}")
        except PermissionError:
            ruta_alt = ruta_resultado.with_name(
                f"{ruta_resultado.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ruta_resultado.suffix}"
            )
            df_trios.to_excel(ruta_alt, index=False)
            print(f"[ADVERTENCIA] No se pudo escribir {ruta_resultado} (archivo en uso). Guardado en: {ruta_alt}")
    else:
        print("[Info] Resultado multiusuario generado sin exportar Excel.")

    return df_trios

def detectar_self_hedging(
    df_base: pd.DataFrame,
    ratio_min_margen: float = 0.03,
    ratio_max_margen: float = 0.05,
    tol_abs: float = 5.0,
    k: float = 0.004,
    tol_max: float | None = None,
    modo_tolerancia: str = "hybrid",
    ruta_resultados: str | Path | None = REPORTS_DIR / "selfhedging_resultado.xlsx",  # CAMBIO
    guardar_detalle: bool = False,
    requerir_tres_selecciones: bool = False,
    progress_callback: ProgressCallback = None,
) -> pd.DataFrame:
    """
    Detecta patrones de self-hedging (mismo usuario cubriendo 1/X/2 en un evento).
    """

    df = df_base.copy()
    # CAMBIO: normalizar seleccion para deteccion (X mayuscula)
    if "sel_norm" not in df.columns:
        base_sel = df["selection_inferida"] if "selection_inferida" in df.columns else df["selection"]
        sel_norm = base_sel.astype(str).str.strip().str.upper()
        sel_norm = sel_norm.replace({"DRAW": "X", "TIE": "X", "D": "X", "0": "X"})
        df["sel_norm"] = sel_norm
    if df.empty:
        print("[Self-hedging] No hay apuestas para analizar.")
        return pd.DataFrame()

    for col_necesaria in ["user_id", "event_name", "apuesta_base"]:
        if col_necesaria not in df.columns:
            print(f"[Self-hedging] Falta columna requerida: {col_necesaria}")
            return pd.DataFrame()

    registros_resumen = []
    registros_detalle = []
    grupos = df.groupby(["user_id", "event_name", "fecha_bucket"])
    total_grupos = len(grupos)
    debug_falta_sel = False
    debug_max_diff = False
    debug_total_zero = False

    # CAMBIO: debug de cobertura por usuario/evento/bucket (>=2 selecciones)
    if total_grupos > 0:
        cobertura_self = (
            df.groupby(["user_id", "event_name", "fecha_bucket", "sel_norm"])["bet_id"]
            .count()
            .unstack(fill_value=0)
        )
        distintos = (cobertura_self > 0).sum(axis=1)
        candidatos = cobertura_self[distintos >= 2]
        if candidatos.empty:
            print("[DEBUG] [Self-hedging] No hay combinaciones >=2 selecciones en el mismo bucket.")
            try:
                print(cobertura_self.head(10))
            except Exception:
                pass

    for idx, ((user_id, ev_name, fecha_bucket), grp) in enumerate(grupos, start=1):
        if progress_callback is not None and total_grupos > 0:
            progress_callback("self_hedging", idx, total_grupos)

        s_by_sel = grp.groupby("sel_norm")["apuesta_base"].sum()
        s_by_sel = s_by_sel[s_by_sel > 0]

        selecciones = [s for s in ["1", "X", "2"] if s in s_by_sel.index]
        if requerir_tres_selecciones:
            if not all(s in s_by_sel.index for s in ["1", "X", "2"]):
                if not debug_falta_sel:
                    print("[DEBUG] [Self-hedging] DESCARTE faltan selecciones user/ev/bucket:", user_id, ev_name, fecha_bucket)
                    debug_falta_sel = True
                continue
        else:
            if len(selecciones) < 2:
                if not debug_falta_sel:
                    print("[DEBUG] [Self-hedging] DESCARTE faltan selecciones user/ev/bucket:", user_id, ev_name, fecha_bucket)
                    debug_falta_sel = True
                continue

        if requerir_tres_selecciones:
            valores = [float(s_by_sel.get("1", 0.0)), float(s_by_sel.get("X", 0.0)), float(s_by_sel.get("2", 0.0))]
        else:
            valores = [float(s_by_sel.get(sel, 0.0)) for sel in selecciones]

        total = float(sum(valores))
        if total <= 0:
            if not debug_total_zero:
                print("[DEBUG] [Self-hedging] DESCARTE total=0 user/ev/bucket:", user_id, ev_name, fecha_bucket)
                debug_total_zero = True
            continue

        if len(valores) == 2:
            max_diff = abs(valores[0] - valores[1])
        else:
            max_diff = max(
                abs(valores[0] - valores[1]),
                abs(valores[0] - valores[2]),
                abs(valores[1] - valores[2]),
            )

        if modo_tolerancia == "ratio":
            tol_val = total * float(ratio_max_margen)
            if max_diff > tol_val:
                if not debug_max_diff:
                    print("[DEBUG] [Self-hedging] DESCARTE max_diff>tol user/ev/bucket:", user_id, ev_name, fecha_bucket)
                    debug_max_diff = True
                continue
            ratio_min_val = float(ratio_min_margen)
            ratio_max_val = float(ratio_max_margen)
            tol_aplicada = float("nan")
        else:
            tol_val = _calcular_tolerancia(total, tol_abs=tol_abs, k=k, tol_max=tol_max)
            if max_diff > tol_val:
                if not debug_max_diff:
                    print("[DEBUG] [Self-hedging] DESCARTE max_diff>tol user/ev/bucket:", user_id, ev_name, fecha_bucket)
                    debug_max_diff = True
                continue
            ratio_eff = (tol_val / total) if total else 0.0
            ratio_min_val = ratio_eff
            ratio_max_val = ratio_eff
            tol_aplicada = tol_val

        dif_rel = (max_diff / total) if total else 0.0

        if dif_rel <= 0.05 and total >= 50:
            nivel_riesgo = "ALTO"
        elif dif_rel <= 0.10 and total >= 20:
            nivel_riesgo = "MEDIO"
        else:
            nivel_riesgo = "BAJO"

        g_prom = float("nan")
        g_min = float("nan")
        g_max = float("nan")
        g_by_sel = None
        if "posible_ganancia" in grp.columns and grp["posible_ganancia"].notna().any():
            g_by_sel = grp.groupby("sel_norm")["posible_ganancia"].sum(min_count=1)
            if requerir_tres_selecciones:
                g_vals = [
                    float(g_by_sel.get("1", float("nan"))),
                    float(g_by_sel.get("X", float("nan"))),
                    float(g_by_sel.get("2", float("nan"))),
                ]
            else:
                g_vals = [float(g_by_sel.get(sel, float("nan"))) for sel in selecciones]
            if not any(pd.isna(v) for v in g_vals):
                g_prom = sum(g_vals) / float(len(g_vals))
                g_min = min(g_vals)
                g_max = max(g_vals)

        stake_total_r = round(total, 2)
        g_prom_r = round(g_prom, 2) if g_prom == g_prom else float("nan")
        g_min_r = round(g_min, 2) if g_min == g_min else float("nan")
        g_max_r = round(g_max, 2) if g_max == g_max else float("nan")
        ratio_min_r = round(ratio_min_val, 4)
        ratio_max_r = round(ratio_max_val, 4)
        dif_rel_r = round(dif_rel, 2)
        tol_aplicada_r = round(tol_aplicada, 2) if tol_aplicada == tol_aplicada else float("nan")
        tol_max_r = round(tol_max, 2) if tol_max is not None else float("nan")

        uid_fmt = _fmt_user_id(user_id)
        selecciones_txt = ",".join(selecciones) if not requerir_tres_selecciones else "1,X,2"

        registros_resumen.append(
            {
                "event_name": ev_name,
                "fecha_bucket": fecha_bucket,
                "usuarios_implicados": uid_fmt,
                "cantidad_usuarios": 1,
                "total_apostado": stake_total_r,
                "posible_ganancia_promedio": g_prom_r,
                "posible_ganancia_min": g_min_r,
                "posible_ganancia_max": g_max_r,
                "ratio_min": ratio_min_r,
                "ratio_max": ratio_max_r,
                "dif_rel_max_vs_total": dif_rel_r,
                "selecciones_por_usuario": f"{uid_fmt}:{selecciones_txt}",
                "nivel_riesgo": nivel_riesgo,
                "tol_aplicada": tol_aplicada_r,
                "tol_abs_usada": float(tol_abs),
                "k_usado": float(k),
                "tol_max_usada": tol_max_r,
            }
        )

        if guardar_detalle:
            for sel in selecciones:
                registros_detalle.append(
                    {
                        "event_name": ev_name,
                        "user_id": uid_fmt,
                        "selection": sel,
                        "apuesta_general": float(s_by_sel.get(sel, 0.0)),
                        "posible_ganancia": float(g_by_sel.get(sel, float("nan"))) if g_by_sel is not None else float("nan"),
                    }
                )

    columnas_resumen = [
        "event_name",
        "fecha_bucket",
        "usuarios_implicados",
        "cantidad_usuarios",
        "total_apostado",
        "posible_ganancia_promedio",
        "posible_ganancia_min",
        "posible_ganancia_max",
        "ratio_min",
        "ratio_max",
        "tol_aplicada",
        "tol_abs_usada",
        "k_usado",
        "tol_max_usada",
        "dif_rel_max_vs_total",
        "selecciones_por_usuario",
        "nivel_riesgo",
    ]
    df_resumen = pd.DataFrame(registros_resumen)
    if not df_resumen.empty:
        df_resumen = df_resumen[columnas_resumen]
        numeric_cols = [
            "total_apostado",
            "posible_ganancia_promedio",
            "posible_ganancia_min",
            "posible_ganancia_max",
            "ratio_min",
            "ratio_max",
            "tol_aplicada",
            "tol_abs_usada",
            "k_usado",
            "tol_max_usada",
            "dif_rel_max_vs_total",
        ]
        for col in numeric_cols:
            df_resumen[col] = df_resumen[col].astype(float).round(2)
    else:
        df_resumen = pd.DataFrame(columns=columnas_resumen)
        print("[Info] No se detectaron patrones de self-hedging.")

    # CAMBIO: permitir ejecucion sin escribir Excel cuando ruta_resultados es None
    if ruta_resultados is not None:
        ruta_resultados = Path(ruta_resultados)
        ruta_resultados.parent.mkdir(parents=True, exist_ok=True)
        df_resumen.to_excel(ruta_resultados, index=False)
        print(f"[Excel] Resultado self-hedging guardado en: {ruta_resultados}")
    else:
        print("[Info] Resultado self-hedging generado sin exportar Excel.")

    if guardar_detalle:
        df_detalle = pd.DataFrame(registros_detalle)
        ruta_detalle = REPORTS_DIR / "self_hedging_detalle.xlsx"
        ruta_detalle.parent.mkdir(parents=True, exist_ok=True)
        # CAMBIO: respetar ausencia de ruta_resultados al guardar detalle
        if ruta_resultados is not None:
            df_detalle.to_excel(ruta_detalle, index=False)
            print(f"[Excel] Detalle self-hedging guardado en: {ruta_detalle}")
        else:
            print("[Info] Detalle self-hedging no exportado (ruta_resultados=None).")

    return df_resumen

# ============================================================
# Reportes JSON / HistÃ³rico
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
    ruta_historico: str | Path = DASHBOARD_DATA_DIR / "historico_riesgo_multicuenta.json",
):
    ruta_historico = Path(ruta_historico)
    ruta_historico.parent.mkdir(parents=True, exist_ok=True)
    meta = reporte_riesgo.get("metadata", {})
    resumen = reporte_riesgo.get("resumen_ejecucion", {})
    est = reporte_riesgo.get("estadisticas_riesgo", {})
    fecha_iso = meta.get("fecha_ejecucion", datetime.now().isoformat(timespec="seconds"))
    fecha_dia = fecha_iso[:10]

    multi = est.get("multiusuario", {}) or {}
    selfh = est.get("self_hedging", {}) or {}

    entry = {
        "id_ejecucion": meta.get("id_ejecucion") or f"EXEC-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "fecha_ejecucion": fecha_dia,
        "total_casos_multi": int(multi.get("casos_totales", 0) or 0),
        "total_casos_self": int(selfh.get("casos_totales", 0) or 0),
        "ratio_sospecha_global": float(resumen.get("ratio_sospecha_global", 0.0)),
        "transacciones_totales": int(resumen.get("total_transacciones", 0) or 0),
    }

    if os.path.exists(ruta_historico):
        try:
            historico = json.load(open(ruta_historico, encoding="utf-8-sig"))
        except Exception:
            historico = {"ejecuciones": []}
    else:
        historico = {"ejecuciones": []}

    historico.setdefault("ejecuciones", []).append(entry)
    with open(ruta_historico, "w", encoding="utf-8-sig") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def generar_reporte_json(
    df_base: pd.DataFrame,
    df_multi: Optional[pd.DataFrame] = None,
    df_self: Optional[pd.DataFrame] = None,
    archivos_entrada: Optional[list] = None,
    total_apuestas_original: Optional[int] = None,
    tolerancia_cobertura: Optional[float] = None,
    min_total_apostado: Optional[float] = None,
    max_apuestas_por_seleccion: Optional[int] = None,
    ratio_min_margen: Optional[float] = None,
    ratio_max_margen: Optional[float] = None,
    tol_abs: Optional[float] = None,
    k: Optional[float] = None,
    tol_max: Optional[float] = None,
    modo_tolerancia: Optional[str] = None,
    tiempo_proceso_seg: Optional[float] = None,
    nombre_archivo: str | Path = DASHBOARD_DATA_DIR / "reporte_riesgo_multicuenta.json",
) -> None:
    """
    Genera un archivo JSON con el resumen de riesgo (multiusuario + self-hedging).
    """

    df_multi = df_multi if df_multi is not None else pd.DataFrame()
    df_self = df_self if df_self is not None else pd.DataFrame()
    archivos_entrada = archivos_entrada or []

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

    # Compatibilidad: si el DF viene con columnas antiguas, generar alias para estadisticas
    if not df_multi.empty and "nivel_riesgo_multi" in df_multi.columns and "nivel_riesgo" not in df_multi.columns:
        df_multi = df_multi.copy()
        df_multi["nivel_riesgo"] = df_multi["nivel_riesgo_multi"]
    if not df_self.empty and "nivel_riesgo_self" in df_self.columns and "nivel_riesgo" not in df_self.columns:
        df_self = df_self.copy()
        df_self["nivel_riesgo"] = df_self["nivel_riesgo_self"]

    niveles_multi = _contar_niveles(df_multi, "nivel_riesgo")
    niveles_self = _contar_niveles(df_self, "nivel_riesgo")

    usuarios_stats = {}

    if not df_multi.empty and "usuarios_implicados" in df_multi.columns:
        for _, row in df_multi.iterrows():
            ev_name = row.get("event_name", "")
            usuarios_str = str(row["usuarios_implicados"])
            usuarios = [u.strip() for u in usuarios_str.split("|") if u.strip()]
            for u in usuarios:
                usuarios_stats.setdefault(u, {"casos_multi": 0, "casos_self": 0, "eventos": set()})
                usuarios_stats[u]["casos_multi"] += 1
                if ev_name:
                    usuarios_stats[u]["eventos"].add(ev_name)

    if not df_self.empty and "usuarios_implicados" in df_self.columns:
        for _, row in df_self.iterrows():
            ev_name = row.get("event_name", "")
            u = str(row["usuarios_implicados"])
            usuarios_stats.setdefault(u, {"casos_multi": 0, "casos_self": 0, "eventos": set()})
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

    parametros_motor = {
        "tolerancia_cobertura": tolerancia_cobertura,
        "min_total_apostado": min_total_apostado,
        "max_apuestas_por_seleccion": max_apuestas_por_seleccion,
        "ratio_min_margen": ratio_min_margen,
        "ratio_max_margen": ratio_max_margen,
        "tol_abs": tol_abs,
        "k": k,
        "tol_max": tol_max,
        "modo_tolerancia": modo_tolerancia,
    }

    reporte_riesgo = {
        "metadata": {
            "nombre_motor": "MultiCuentaRiskEngine",
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
        "parametros_motor": parametros_motor,
    }

    nombre_archivo = Path(nombre_archivo)
    nombre_archivo.parent.mkdir(parents=True, exist_ok=True)

    with open(nombre_archivo, "w", encoding="utf-8-sig") as f:
        json.dump(reporte_riesgo, f, ensure_ascii=False, indent=2)

    print(f"[JSON] Reporte guardado en: {nombre_archivo}")
    try:
        actualizar_historico_riesgo(reporte_riesgo)
    except Exception as e:
        print("[ADVERTENCIA] No se pudo actualizar el histÃ³rico de riesgo:")
        print(e)


# ============================================================
# Orquestador
# ============================================================

def ejecutar_motor_multicuenta(
    df_base: pd.DataFrame,
    tolerancia_cobertura: float = 0.10,
    min_total_apostado: float = 0.0,
    max_apuestas_por_seleccion: int = 20,
    ratio_min_margen: float = 0.03,
    ratio_max_margen: float = 0.05,
    tol_abs: float = 5.0,
    k: float = 0.004,
    tol_max: float | None = None,
    modo_tolerancia: str = "hybrid",
    requerir_tres_selecciones: bool = False,
    ruta_multi: str | Path | None = None,
    ruta_self: str | Path | None = None,
    ruta_json: str | Path | None = None,
    generar_reporte: bool = True,
    progress_callback: ProgressCallback = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Ejecuta detecciÃ³n multiusuario y self-hedging usando UNA base ya preparada.
    """
    print("\n================= INICIANDO MOTOR MULTI-CUENTA =================\n")

    ruta_multi = Path(ruta_multi) if ruta_multi is not None else REPORTS_DIR / "multi_cuenta_resultado.xlsx"
    ruta_self = Path(ruta_self) if ruta_self is not None else REPORTS_DIR / "selfhedging_resultado.xlsx"
    ruta_json = Path(ruta_json) if ruta_json is not None else DASHBOARD_DATA_DIR / "reporte_riesgo_multicuenta.json"

    df_multi = detectar_trios_multiusuario(
        df_base,
        tolerancia_cobertura=tolerancia_cobertura,
        min_total_apostado=min_total_apostado,
        max_apuestas_por_seleccion=max_apuestas_por_seleccion,
        ratio_min_margen=ratio_min_margen,
        ratio_max_margen=ratio_max_margen,
        tol_abs=tol_abs,
        k=k,
        tol_max=tol_max,
        modo_tolerancia=modo_tolerancia,
        ruta_resultado=ruta_multi,
        progress_callback=progress_callback,
    )

    df_self = detectar_self_hedging(
        df_base,
        ratio_min_margen=ratio_min_margen,
        ratio_max_margen=ratio_max_margen,
        tol_abs=tol_abs,
        k=k,
        tol_max=tol_max,
        modo_tolerancia=modo_tolerancia,
        guardar_detalle=False,
        requerir_tres_selecciones=requerir_tres_selecciones,
        ruta_resultados=ruta_self,
        progress_callback=progress_callback,
    )

    if generar_reporte:
        generar_reporte_json(
            df_base=df_base,
            df_multi=df_multi,
            df_self=df_self,
            tolerancia_cobertura=tolerancia_cobertura,
            min_total_apostado=min_total_apostado,
            max_apuestas_por_seleccion=max_apuestas_por_seleccion,
            ratio_min_margen=ratio_min_margen,
            ratio_max_margen=ratio_max_margen,
            tol_abs=tol_abs,
            k=k,
            tol_max=tol_max,
            modo_tolerancia=modo_tolerancia,
            nombre_archivo=ruta_json,
        )

    print("\n================= MOTOR MULTI-CUENTA FINALIZADO =================\n")
    return df_multi, df_self
