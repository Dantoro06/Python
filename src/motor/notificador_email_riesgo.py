"""Alertas independientes; por defecto solo simula y no envía correos."""

import os
import json
import smtplib
import hashlib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

try:
    from utils.paths_dashboard import DASHBOARD_DATA_DIR
except ImportError:
    from src.utils.paths_dashboard import DASHBOARD_DATA_DIR


MOTORES = {
    "multi_cuenta": "Multi-Cuenta",
    "multiusuario": "Multi-Cuenta",
    "self_hedging": "Self-Hedging",
    "bonus_abuse": "Abuso de Bonos",
}
INDICADORES = {
    "multi_cuenta": "Multi-Cuenta",
    "self_hedging": "Self-Hedging",
    "bonus_abuse": "Abuso de Bonos",
    "ratio_alto": "Ratio alto",
    "retiro_rapido": "Retiro rápido",
    "frecuencia_alta": "Frecuencia alta",
}


def _texto(valor):
    if valor is None or valor == "" or (isinstance(valor, float) and valor != valor):
        return "—"
    return str(valor)


def _indicadores(valor):
    if not isinstance(valor, str) or not valor:
        return _texto(valor)
    return " · ".join(INDICADORES.get(parte.strip(), parte) for parte in valor.split("|"))


def _serializar(valor):
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _evento(registro):
    nombre = registro.get("event_name")
    if nombre is None or not str(nombre).strip():
        return None
    return [registro.get("motor"), nombre, registro.get("fecha_bucket")]


def _unicos(valores):
    resultado = []
    for valor in valores:
        if _texto(valor) != "—" and valor not in resultado:
            resultado.append(valor)
    return resultado


def _guardar_historico(ruta, historico):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(json.dumps(historico, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(ruta)


def procesar_alertas_email(
    registros, niveles_alerta=("CRITICO", "ALTO"), dry_run=True, ruta_historico=None
):
    """Envía al mismo buzón RISK_ALERT_EMAIL usado como remitente.

    candidatas cuenta identidades elegibles únicas; omitidas_duplicadas cuenta
    las ya enviadas. alertas describe las pendientes, simuladas o intentadas.
    Debe ejecutarse sin llamadas concurrentes sobre el mismo histórico.
    """
    resumen = {
        "candidatas": 0, "enviadas": 0, "omitidas_duplicadas": 0,
        "errores": [], "dry_run": dry_run, "alertas": [],
    }
    if not isinstance(registros, list) or not all(isinstance(r, dict) for r in registros):
        resumen["errores"].append("registros debe ser una lista de diccionarios.")
        return resumen

    ruta = Path(ruta_historico) if ruta_historico is not None else (
        DASHBOARD_DATA_DIR / "alertas_email_enviadas.json"
    )
    try:
        if ruta.exists():
            with ruta.open(encoding="utf-8-sig") as archivo:
                historico = json.load(archivo)
        else:
            historico = []
        if not isinstance(historico, list) or not all(
            isinstance(r, dict) and isinstance(r.get("alert_id"), str) for r in historico
        ):
            raise ValueError("Histórico inválido")
    except (OSError, ValueError):
        resumen["errores"].append("No se pudo leer un histórico válido; no se enviaron alertas.")
        return resumen

    enviadas = {r["alert_id"] for r in historico}
    grupos = {}
    usuarios_evento = {}
    for registro in registros:
        evento = _evento(registro)
        if evento is not None:
            usuarios_evento.setdefault(_serializar(evento), []).append(registro.get("user_id"))
        if registro.get("nivel_riesgo") not in niveles_alerta:
            continue
        campos = ("motor", "event_name", "fecha_bucket", "nivel_riesgo") if evento is not None else (
            "motor", "user_id", "nivel_riesgo", "flags", "evidencia"
        )
        identidad = {campo: registro.get(campo) for campo in campos}
        alert_id = hashlib.sha256(_serializar(identidad).encode("utf-8")).hexdigest()
        grupos.setdefault(alert_id, []).append(registro)

    resumen["candidatas"] = len(grupos)
    for alert_id, grupo in grupos.items():
        if alert_id in enviadas:
            resumen["omitidas_duplicadas"] += 1
            continue
        registro = grupo[0]
        evento = _evento(registro)
        usuarios = _unicos(usuarios_evento[_serializar(evento)]) if evento is not None else (
            _unicos([registro.get("user_id")])
        )
        puntajes = _unicos(r.get("score") for r in grupo)
        indicadores = _unicos(_indicadores(r.get("flags")) for r in grupo)
        motor = registro.get("motor")
        nivel = registro.get("nivel_riesgo")
        cuerpo = "\n".join([
            "Risk Monitor PRO — Alerta de riesgo", "",
            "Usuario: " + (", ".join(_texto(u) for u in usuarios) or "—"),
            "Riesgo detectado: " + _texto(MOTORES.get(motor, motor)),
            "Nivel de riesgo: " + _texto(nivel),
            "Puntaje: " + (" · ".join(_texto(p) for p in puntajes) or "—"),
            "Indicadores: " + (" · ".join(indicadores) or "—"),
            "Evento: " + _texto(registro.get("event_name")),
            "Ventana temporal: " + _texto(registro.get("fecha_bucket")), "",
            "Estado: Pendiente de revisión",
        ])
        resumen["alertas"].append({
            "alert_id": alert_id, "user_id": usuarios,
            "motor": motor, "nivel_riesgo": nivel,
            "event_name": registro.get("event_name"),
            "asunto": f"Risk Monitor PRO — Alerta de riesgo {nivel}",
            "cuerpo": cuerpo, "estado": "simulada" if dry_run else "pendiente",
        })

    if dry_run or not resumen["alertas"]:
        return resumen
    correo = os.environ.get("RISK_ALERT_EMAIL", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not correo or not password.strip():
        resumen["errores"].append("Faltan RISK_ALERT_EMAIL o GMAIL_APP_PASSWORD.")
        return resumen

    for alerta in resumen["alertas"]:
        try:
            mensaje = EmailMessage()
            mensaje["From"] = correo
            mensaje["To"] = correo
            mensaje["Subject"] = alerta["asunto"]
            mensaje.set_content(alerta["cuerpo"])
            smtp = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
            try:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(correo, password)
                rechazados = smtp.send_message(mensaje)
                if rechazados:
                    raise smtplib.SMTPException("Destinatario rechazado")
            finally:
                smtp.close()
        except Exception:
            alerta["estado"] = "error_envio"
            resumen["errores"].append({"alert_id": alerta["alert_id"], "error": "No se pudo enviar el correo."})
            continue

        resumen["enviadas"] += 1
        alerta["estado"] = "enviada"
        historico.append({
            "alert_id": alerta["alert_id"],
            "fecha_envio": datetime.now().astimezone().isoformat(timespec="microseconds"),
            "user_id": alerta["user_id"], "motor": alerta["motor"],
            "nivel_riesgo": alerta["nivel_riesgo"], "event_name": alerta["event_name"],
        })
        try:
            _guardar_historico(ruta, historico)
        except (OSError, ValueError):
            alerta["estado"] = "enviada_sin_historico"
            resumen["errores"].append({
                "alert_id": alerta["alert_id"],
                "error": "Correo enviado, pero no se pudo guardar el histórico; se detuvo el lote.",
            })
            break
    return resumen
