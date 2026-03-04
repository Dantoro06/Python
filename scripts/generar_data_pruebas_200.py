from __future__ import annotations

from pathlib import Path
import random
import pandas as pd


def _row(
    user_id: int,
    bet_id: int,
    fecha: str,
    event_name: str,
    sport: str,
    market: str,
    selection: str,
    stake: float,
    net_price: float = 3.0,
    bet_status: str = "open",
    ticket_id: str | None = None,
) -> dict:
    return {
        "user_id": user_id,
        "bet_id": bet_id,
        "ticket_id": ticket_id or f"TKT_{bet_id:06d}",
        "fecha_apuesta": fecha,
        "event_name": event_name,
        "sport": sport,
        "market": market,
        "selection": selection,
        "stake": stake,
        "net_price": net_price,
        "bet_status": bet_status,
    }


def generar_base_apuestas_200() -> pd.DataFrame:
    rows: list[dict] = []
    bet_id = 1

    # Seeds multi-cuenta (1/X/2 por evento, usuarios distintos)
    seeds_mu = [
        ("MU_MATCH_001", [501, 502, 503], ["1", "X", "2"], [100, 100, 100], "2026-01-05 10:01:01"),
        ("MU_MATCH_002", [511, 512, 513], ["1", "X", "2"], [80, 81, 79], "2026-01-05 10:02:01"),
        ("MU_MATCH_003", [521, 522, 523], ["1", "X", "2"], [120, 119, 121], "2026-01-05 10:03:01"),
    ]
    for event_name, users, sels, stakes, fecha in seeds_mu:
        for uid, sel, stk in zip(users, sels, stakes):
            rows.append(_row(uid, bet_id, fecha, event_name, "soccer", "1x2", sel, float(stk)))
            bet_id += 1

    # Seeds self-hedging (1/X/2 por evento, mismo usuario)
    seeds_sh = [
        ("SH_MATCH_001", 601, "2026-01-05 10:11:10", [60, 60, 60]),
        ("SH_MATCH_002", 611, "2026-01-05 10:12:10", [70, 69, 71]),
        ("SH_MATCH_003", 621, "2026-01-05 10:13:10", [90, 89, 91]),
    ]
    for event_name, uid, fecha, stakes in seeds_sh:
        for sel, stk in zip(["1", "X", "2"], stakes):
            rows.append(_row(uid, bet_id, fecha, event_name, "soccer", "1x2", sel, float(stk)))
            bet_id += 1

    # Filler para llegar a 200 filas (sin generar coberturas 1X2)
    rnd = random.Random(42)
    sports = ["basketball", "tennis", "soccer"]
    markets = ["over_under", "asian_handicap", "both_teams_score"]
    selections = ["over", "under", "yes", "no", "home", "away"]
    while len(rows) < 200:
        user_id = rnd.randint(7000, 7099)
        fecha = f"2026-01-{rnd.randint(6, 28):02d} {rnd.randint(0, 23):02d}:{rnd.randint(0, 59):02d}:00"
        event_name = f"NOISE_MATCH_{rnd.randint(1, 80):03d}"
        sport = rnd.choice(sports)
        market = rnd.choice(markets)
        selection = rnd.choice(selections)
        stake = round(rnd.uniform(5, 150), 2)
        net_price = round(rnd.uniform(1.1, 4.0), 2)
        rows.append(_row(user_id, bet_id, fecha, event_name, sport, market, selection, stake, net_price=net_price))
        bet_id += 1

    return pd.DataFrame(rows)


def generar_base_bonos() -> pd.DataFrame:
    # 9001 -> ALTO (ratio alto + retiro rapido = 75)
    # 9002 -> CRITICO (ratio alto + retiro rapido + frecuencia alta = 100)
    # 9003 -> MEDIO (ratio alto = 40)
    rows = [
        {
            "user_id": 9001,
            "estado_bono": "LIBERADO",
            "monto_bono": 200.0,
            "deposito": 100.0,
            "fecha_bono": "2026-01-01 08:00:00",
            "fecha_retiro": "2026-01-01 18:00:00",
        },
        {
            "user_id": 9002,
            "estado_bono": "RETIRADO",
            "monto_bono": 240.0,
            "deposito": 100.0,
            "fecha_bono": "2026-01-01 09:00:00",
            "fecha_retiro": "2026-01-01 12:00:00",
        },
        {
            "user_id": 9002,
            "estado_bono": "RETIRADO",
            "monto_bono": 210.0,
            "deposito": 100.0,
            "fecha_bono": "2026-01-02 09:00:00",
            "fecha_retiro": "2026-01-02 12:00:00",
        },
        {
            "user_id": 9002,
            "estado_bono": "RETIRADO",
            "monto_bono": 220.0,
            "deposito": 100.0,
            "fecha_bono": "2026-01-03 09:00:00",
            "fecha_retiro": "2026-01-03 12:00:00",
        },
        {
            "user_id": 9003,
            "estado_bono": "PENDIENTE",
            "monto_bono": 180.0,
            "deposito": 100.0,
            "fecha_bono": "2026-01-04 10:00:00",
            "fecha_retiro": None,
        },
    ]
    return pd.DataFrame(rows)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "tests" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    path_apuestas = out_dir / "base_apuestas_pruebas_200.xlsx"
    path_bonos = out_dir / "base_bonos_pruebas.xlsx"

    df_apuestas = generar_base_apuestas_200()
    df_bonos = generar_base_bonos()

    df_apuestas.to_excel(path_apuestas, index=False)
    df_bonos.to_excel(path_bonos, index=False)

    print(f"[OK] Apuestas: {path_apuestas} ({len(df_apuestas)} filas)")
    print(f"[OK] Bonos:    {path_bonos} ({len(df_bonos)} filas)")


if __name__ == "__main__":
    main()
