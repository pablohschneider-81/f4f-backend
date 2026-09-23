# agent/notifications.py — Notificaciones por email a Hernán (vía Resend)
# Generado por AgentKit

"""
Avisa por email cuando alguien muestra interés real (lead) o pide una
mentoría por el chat. Usa la API HTTP de Resend (https://resend.com) en
vez de SMTP directo — los hostings gratuitos (como el plan free de Render)
suelen bloquear el puerto SMTP saliente, pero HTTPS (443) siempre funciona.

En vez de mandar la conversación completa, le pedimos a Gemini que
extraiga solo lo esencial (nombre, día/horario, contacto) — así el email
es corto y directo, sin que Hernán tenga que leer todo el chat.
"""

import os
import json
import html
import logging
import httpx
from datetime import datetime

from agent.brain import client, MODEL

logger = logging.getLogger("agentkit")

RESEND_API_URL = "https://api.resend.com/emails"

# Tokens de marca F4F (ver skill fittest4fit-marca / brand-book.md)
_BG = "#04101F"
_INK = "#F4F7FB"
_CYAN = "#00C2FF"
_GOLD = "#FFB830"
_SLATE = "#8FA3B8"
_CARD_BG = "#0d1f33"

_SIN_DATO = "No especificado"


def notificaciones_configuradas() -> bool:
    """True si las variables de entorno necesarias están cargadas."""
    return bool(os.getenv("RESEND_API_KEY") and os.getenv("NOTIFY_EMAIL_TO"))


async def extraer_datos_lead(historial: list[dict]) -> dict:
    """
    Le pide a Gemini que extraiga solo nombre, día/horario y contacto
    (email o teléfono) de la conversación. Si algo no aparece, devuelve
    "No especificado" en ese campo — nunca inventa datos.
    """
    transcripcion = "\n".join(
        f"{'Cliente' if m['role'] == 'user' else 'Agente'}: {m['content']}"
        for m in historial[-12:]
    )
    prompt = (
        "De la siguiente conversación de atención al cliente, extraé SOLO estos "
        "3 datos si aparecen explícitamente: el nombre del cliente, el día y "
        "horario de disponibilidad que dio, y su contacto (email o teléfono). "
        f'Si un dato no aparece en la conversación, usá el string "{_SIN_DATO}" '
        "para ese campo — NUNCA inventes ni asumas un dato que no esté escrito. "
        'Respondé ÚNICAMENTE con un JSON válido, sin texto antes ni después, '
        'con exactamente estas claves: "nombre", "dia_hora", "contacto".\n\n'
        f"Conversación:\n{transcripcion}"
    )

    try:
        response = client.models.generate_content(model=MODEL, contents=prompt)
        texto = (response.text or "").strip()

        # Por si Gemini envuelve la respuesta en un bloque ```json ... ```
        if texto.startswith("```"):
            texto = texto.strip("`").strip()
            if texto.lower().startswith("json"):
                texto = texto[4:].strip()

        datos = json.loads(texto)
        return {
            "nombre": str(datos.get("nombre") or _SIN_DATO),
            "dia_hora": str(datos.get("dia_hora") or _SIN_DATO),
            "contacto": str(datos.get("contacto") or _SIN_DATO),
        }
    except Exception as e:
        logger.warning(f"No se pudieron extraer los datos del lead: {e}")
        return {"nombre": _SIN_DATO, "dia_hora": _SIN_DATO, "contacto": _SIN_DATO}


def _construir_html(identificador: str, fecha: str, datos: dict) -> str:
    """Arma el cuerpo HTML del email, on-brand F4F. Estilos inline (los clientes de mail ignoran <style>)."""

    def _campo(etiqueta: str, valor: str) -> str:
        return f"""
        <tr>
          <td style="padding-bottom:16px;">
            <div style="font-family:'Courier New',monospace;font-size:11px;letter-spacing:0.08em;color:{_CYAN};margin-bottom:4px;">{etiqueta}</div>
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:16px;color:{_INK};">{html.escape(valor)}</div>
          </td>
        </tr>"""

    return f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background-color:{_BG};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{_BG};padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background-color:{_BG};">

          <tr>
            <td style="padding-bottom:20px;border-bottom:1px solid #0d2540;">
              <span style="display:inline-block;font-family:'Courier New',monospace;font-size:11px;letter-spacing:0.1em;color:{_GOLD};border:1px solid {_GOLD};border-radius:3px;padding:4px 10px;">NUEVO LEAD</span>
              <div style="font-family:Georgia,'Times New Roman',serif;font-size:26px;color:{_INK};margin-top:14px;">
                F4F Assistant
              </div>
              <div style="font-family:'Courier New',monospace;font-size:12px;color:{_SLATE};margin-top:4px;">
                {html.escape(fecha)} &middot; fittest4fit.com
              </div>
            </td>
          </tr>

          <tr>
            <td style="background-color:{_CARD_BG};border-left:3px solid {_CYAN};border-radius:4px;padding:20px 22px;margin-top:20px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                {_campo("NOMBRE", datos["nombre"])}
                {_campo("DÍA Y HORARIO", datos["dia_hora"])}
                {_campo("CONTACTO", datos["contacto"])}
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding-top:20px;">
              <div style="font-family:'Courier New',monospace;font-size:11px;color:{_SLATE};">
                Identificador de la conversación: {html.escape(identificador)}
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding-top:16px;border-top:1px solid #0d2540;margin-top:16px;">
              <div style="font-family:'Courier New',monospace;font-size:11px;color:{_SLATE};padding-top:16px;display:block;">
                Fittest4Fit &middot; F4F Assistant &middot; no respondas a este email, es automatico
              </div>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


async def enviar_notificacion_lead(identificador: str, historial: list[dict]) -> None:
    """
    Envía un email corto a Hernán con solo nombre, día/horario y contacto
    del lead, extraídos de la conversación reciente.

    Args:
        identificador: teléfono (WhatsApp) o "web:<session_id>" (widget web)
        historial: conversación reciente [{"role": "user/assistant", "content": "..."}]
    """
    if not notificaciones_configuradas():
        logger.warning(
            "Notificaciones por email no configuradas "
            "(faltan RESEND_API_KEY / NOTIFY_EMAIL_TO en el .env)"
        )
        return

    api_key = os.getenv("RESEND_API_KEY")
    destinatario = os.getenv("NOTIFY_EMAIL_TO")
    remitente = os.getenv("NOTIFY_EMAIL_FROM", "F4F Assistant <onboarding@resend.dev>")
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    datos = await extraer_datos_lead(historial)

    cuerpo_plano = (
        "Nuevo lead desde el chat de Fittest4Fit\n\n"
        f"Nombre: {datos['nombre']}\n"
        f"Dia y horario: {datos['dia_hora']}\n"
        f"Contacto: {datos['contacto']}\n\n"
        f"Fecha: {fecha}\n"
        f"Identificador: {identificador}\n"
    )

    payload = {
        "from": remitente,
        "to": [destinatario],
        "subject": "Nuevo lead - F4F Assistant",
        "html": _construir_html(identificador, fecha, datos),
        "text": cuerpo_plano,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as http_client:
            r = await http_client.post(
                RESEND_API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        if r.status_code >= 400:
            logger.error(f"Error enviando notificacion por email (Resend {r.status_code}): {r.text}")
        else:
            logger.info(f"Notificacion de lead enviada a {destinatario}")
    except Exception as e:
        logger.error(f"Error enviando notificacion por email: {e}")
