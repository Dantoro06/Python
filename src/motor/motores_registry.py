# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

import pandas as pd

try:
    from motor.pipeline_wrappers import (
        wrapper_bonus_abuse,
        wrapper_multi_cuenta,
        wrapper_self_hedging,
    )
except Exception:
    from pipeline_wrappers import (
        wrapper_bonus_abuse,
        wrapper_multi_cuenta,
        wrapper_self_hedging,
    )


@dataclass(frozen=True)
class MotorSpec:
    nombre: str
    habilitado_por_defecto: bool
    tipo_salida: str
    funcion_ejecucion: Callable[..., pd.DataFrame]
    requiere_df_base: bool
    requiere_df_raw: bool
    requiere_bonos: bool
    descripcion: str


def get_motores_registry() -> Dict[str, MotorSpec]:
    return {
        "multi_cuenta": MotorSpec(
            nombre="multi_cuenta",
            habilitado_por_defecto=True,
            tipo_salida="usuario",
            funcion_ejecucion=wrapper_multi_cuenta,
            requiere_df_base=True,
            requiere_df_raw=False,
            requiere_bonos=False,
            descripcion="Detecta triadas 1X2 entre usuarios (multiusuario).",
        ),
        "self_hedging": MotorSpec(
            nombre="self_hedging",
            habilitado_por_defecto=True,
            tipo_salida="usuario",
            funcion_ejecucion=wrapper_self_hedging,
            requiere_df_base=True,
            requiere_df_raw=False,
            requiere_bonos=False,
            descripcion="Detecta coberturas 1X2 dentro del mismo usuario.",
        ),
        "bonus_abuse": MotorSpec(
            nombre="bonus_abuse",
            habilitado_por_defecto=True,
            tipo_salida="usuario",
            funcion_ejecucion=wrapper_bonus_abuse,
            requiere_df_base=False,
            requiere_df_raw=True,
            requiere_bonos=True,
            descripcion="Detecta abuso de bonos y resume riesgo por usuario.",
        ),
    }


# Estructura lista para futuros motores (no implementados aun):
FUTUROS_MOTORES_TEMPLATE = [
    {
        "nombre": "cashflow_anomalo",
        "habilitado_por_defecto": False,
        "funcion_ejecucion": "wrapper_cashflow_anomalo",
        "requiere_df_base": False,
        "requiere_df_raw": True,
        "requiere_bonos": False,
        "descripcion": "Detecta ciclos deposito-apuesta-retiro anomalos",
    },
    {
        "nombre": "ip_device_shared",
        "habilitado_por_defecto": False,
        "funcion_ejecucion": "wrapper_ip_device_shared",
        "requiere_df_base": False,
        "requiere_df_raw": True,
        "requiere_bonos": False,
        "descripcion": "Detecta cuentas con IP o dispositivo compartido",
    },
    {
        "nombre": "payment_instrument_shared",
        "habilitado_por_defecto": False,
        "funcion_ejecucion": "wrapper_payment_instrument_shared",
        "requiere_df_base": False,
        "requiere_df_raw": True,
        "requiere_bonos": False,
        "descripcion": "Detecta medios de pago compartidos entre cuentas",
    },
    {
        "nombre": "velocidad_operacional",
        "habilitado_por_defecto": False,
        "funcion_ejecucion": "wrapper_velocidad_operacional",
        "requiere_df_base": False,
        "requiere_df_raw": True,
        "requiere_bonos": False,
        "descripcion": "Detecta patrones de operacion anormalmente rapidos",
    },
]

