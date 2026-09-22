# agent/notifications.py — Notificaciones por email a Hernán (vía Resend)
# Generado por AgentKit

"""
Avisa por email cuando alguien muestra interés real (lead) o pide una
mentoría por el chat. Usa la API HTTP de Resend (https://resend.com) en
vez de SMTP directo — los hostings gratuitos (como el plan free de Render)
suelen bloquear el puerto SMTP saliente, pero HTTPS (443) siempre funciona.

El email se manda en HTML con la identidad visual de Fittest4Fit (fondo
navy, tipografía serif, acento dorado) para que se distinga de un vistazo
en la bandeja de entrada — con una versión en texto plano de respaldo para
clientes de correo que no rendericen HTML.
"""

import os
import html
import logging
import httpx
from datetime import datetime

logger = logging.getLogger("agentkit")

RESEND_API_URL = "https://api.resend.com/emails"

# Tokens de marca F4F (ver skill fittest4fit-marca / brand-book.md)
_BG = "#04101F"
_INK = "#F4F7FB"
_CYAN = "#00C2FF"
_GOLD = "#FFB830"
_SLATE = "#8FA3B8"
_CARD_BG = "#0d1f33"


def notificaciones_configuradas() -> bool:
    """True si las variables de entorno necesarias están cargadas."""
    return bool(os.getenv("RESEND_API_KEY") and os.getenv("NOTIFY_EMAIL_TO"))


def _construir_html(identificador: str, fecha: str, mensaje_disparador: str, historial: list[dict]) -> str:
    """Arma el cuerpo HTML del email, on-brand F4F. Estilos inline (los clientes de mail ignoran <style>)."""
    filas_conversacion = ""
    for m in historial[-10:]:
        es_cliente = m["role"] == "user"
        etiqueta = "CLIENTE" if es_cliente else "F4F ASSISTANT"
        color_etiqueta = _CYAN if es_cliente else _SLATE
        texto = html.escape(m["content"]).replace("\n", "<br>")
        filas_conversacion += f"""
        <div style="margin:0 0 14px 0;">
          <div style="font-family:'Courier New',monospace;font-size:11px;letter-spacing:0.08em;color:{color_etiqueta};margin-bottom:4px;">{etiqueta}</div>
          <div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:{_INK};">{texto}</div>
        </div>"""

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
                Aviso automatico desde el chat de fittest4fit.com
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding:20px 0;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="font-family:'Courier New',monospace;font-size:11px;color:{_SLATE};padding-bottom:4px;">IDENTIFICADOR</td>
                </tr>
                <tr>
                  <td style="font-family:Arial,sans-serif;font-size:14px;color:{_INK};padding-bottom:14px;">{html.escape(identificador)}</td>
                </tr>
                <tr>
                  <td style="font-family:'Courier New',monospace;font-size:11px;color:{_SLATE};padding-bottom:4px;">FECHA</td>
                </tr>
                <tr>
                  <td style="font-family:Arial,sans-serif;font-size:14px;color:{_INK};padding-bottom:14px;">{html.escape(fecha)}</td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="background-color:{_CARD_BG};border-left:3px solid {_CYAN};border-radius:4px;padding:16px 18px;">
              <div style="font-family:'Courier New',monospace;font-size:11px;letter-spacing:0.08em;color:{_CYAN};margin-bottom:6px;">MENSAJE QUE DISPARO EL AVISO</div>
              <div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.5;color:{_INK};">{html.escape(mensaje_disparador)}</div>
            </td>
          </tr>

          <tr>
            <td style="padding:24px 0 8px 0;">
              <div style="font-family:Georgia,'Times New Roman',serif;font-size:16px;color:{_INK};border-bottom:1px solid #0d2540;padding-bottom:10px;margin-bottom:16px;">
                Conversacion reciente
              </div>
              {filas_conversacion}
            </td>
          </tr>

          <tr>
            <td style="padding-top:16px;border-top:1px solid #0d2540;">
              <div style="font-family:'Courier New',monospace;font-size:11px;color:{_SLATE};">
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


async def enviar_notificacion_lead(identificador: str, mensaje_disparador: str, historial: list[dict]) -> None:
    """
    Envía un email a Hernán avisando que alguien mostró interés real en un
    programa o pidió una mentoría, con la conversación reciente como contexto.

    Args:
        identificador: teléfono (WhatsApp) o "web:<session_id>" (widget web)
        mensaje_disparador: el mensaje del cliente que activó el aviso
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

    transcripcion_plana = "\n".join(
        f"{'Cliente' if m['role'] == 'user' else 'F4F Assistant'}: {m['content']}"
        for m in historial[-10:]
    )
    cuerpo_plano = (
        "Nuevo lead / posible mentoria desde el chat de Fittest4Fit\n\n"
        f"Identificador de la conversacion: {identificador}\n"
        f"Fecha: {fecha}\n"
        f"Mensaje que disparo el aviso: {mensaje_disparador}\n\n"
        "--- Conversacion reciente ---\n"
        f"{transcripcion_plana}\n"
    )

    payload = {
        "from": remitente,
        "to": [destinatario],
        "subject": "Nuevo lead - F4F Assistant",
        "html": _construir_html(identificador, fecha, mensaje_disparador, historial),
        "text": cuerpo_plano,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
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
