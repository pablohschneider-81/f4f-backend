# agent/main.py — Servidor FastAPI: widget web + (opcional) webhook de WhatsApp
# Generado por AgentKit

"""
Servidor principal del agente de Fittest4Fit.

Siempre expone /chat/web (para el widget embebido en la landing).
Si WHATSAPP_PROVIDER está configurado en el .env, además expone /webhook
para conectar WhatsApp (Twilio o Meta) más adelante — no hace falta para
que el widget web funcione.
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial
from agent.tools import calificar_lead
from agent.notifications import enviar_notificacion_lead

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

PORT = int(os.getenv("PORT", 8000))

# Los orígenes que pueden llamar al widget (tu web). "*" = cualquiera,
# más simple para empezar; podés restringirlo a tu dominio más adelante
# con ALLOWED_ORIGINS=https://fittest4fit.com en las variables de entorno.
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]

# El proveedor de WhatsApp es opcional — el widget web funciona sin él
WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "").lower()
proveedor = None
if WHATSAPP_PROVIDER:
    from agent.providers import obtener_proveedor
    proveedor = obtener_proveedor()

# ── Notificación de leads con "debounce" ───────────────────────────────
# Cuando se detecta interés real, NO mandamos el email al toque: esperamos
# unos segundos por si el cliente sigue completando datos (día, hora,
# motivo) en mensajes separados. Si llega un mensaje nuevo de esa misma
# conversación antes de que se cumpla la espera, la reiniciamos. Al final
# se manda UN SOLO email con la conversación completa hasta ese momento.
NOTIFICACION_DEBOUNCE_SEGUNDOS = 60

_leads_activos: set[str] = set()
_notificaciones_pendientes: dict[str, asyncio.Task] = {}


async def _enviar_notificacion_con_espera(identificador: str, mensaje_disparador: str) -> None:
    """Espera NOTIFICACION_DEBOUNCE_SEGUNDOS y manda el email con el historial más reciente."""
    try:
        await asyncio.sleep(NOTIFICACION_DEBOUNCE_SEGUNDOS)
    except asyncio.CancelledError:
        # Llegó un mensaje nuevo antes de tiempo — la nueva tarea programada se encarga
        return
    historial_actual = await obtener_historial(identificador)
    await enviar_notificacion_lead(identificador, mensaje_disparador, historial_actual)
    _notificaciones_pendientes.pop(identificador, None)


def _programar_notificacion_lead(identificador: str, mensaje_disparador: str) -> None:
    """Marca la conversación como lead y (re)programa el envío del email, cancelando la espera anterior si había."""
    _leads_activos.add(identificador)
    tarea_previa = _notificaciones_pendientes.get(identificador)
    if tarea_previa and not tarea_previa.done():
        tarea_previa.cancel()
    _notificaciones_pendientes[identificador] = asyncio.create_task(
        _enviar_notificacion_con_espera(identificador, mensaje_disparador)
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos al arrancar el servidor."""
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Servidor F4F Assistant corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__ if proveedor else 'no configurado (solo widget web)'}")
    yield


app = FastAPI(
    title="F4F Assistant — Agente de Fittest4Fit",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/")
async def health_check():
    """Endpoint de salud para Render/monitoreo."""
    return {"status": "ok", "service": "f4f-assistant"}


class ChatWebRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=1000)


@app.post("/chat/web")
async def chat_web(payload: ChatWebRequest):
    """
    Endpoint que consume el widget de chat embebido en la landing.
    Usa el mismo cerebro (brain.py) y memoria (memory.py) que WhatsApp,
    pero identifica la conversación por session_id en vez de teléfono.
    """
    telefono_virtual = f"web:{payload.session_id}"
    historial = await obtener_historial(telefono_virtual)
    respuesta = await generar_respuesta(payload.message, historial)
    await guardar_mensaje(telefono_virtual, "user", payload.message)
    await guardar_mensaje(telefono_virtual, "assistant", respuesta)

    if calificar_lead(payload.message) == "alto" or telefono_virtual in _leads_activos:
        _programar_notificacion_lead(telefono_virtual, payload.message)

    return {"reply": respuesta}


# ── WhatsApp (opcional) — solo se registra si WHATSAPP_PROVIDER está en .env ──
if proveedor is not None:

    @app.get("/webhook")
    async def webhook_verificacion(request: Request):
        """Verificación GET del webhook (requerido por Meta Cloud API, no-op para otros)."""
        resultado = await proveedor.validar_webhook(request)
        if resultado is not None:
            return PlainTextResponse(str(resultado))
        return {"status": "ok"}

    @app.post("/webhook")
    async def webhook_handler(request: Request):
        """Recibe mensajes de WhatsApp via el proveedor configurado."""
        try:
            mensajes = await proveedor.parsear_webhook(request)

            for msg in mensajes:
                if msg.es_propio or not msg.texto:
                    continue

                logger.info(f"Mensaje de {msg.telefono}: {msg.texto}")

                historial = await obtener_historial(msg.telefono)
                respuesta = await generar_respuesta(msg.texto, historial)

                await guardar_mensaje(msg.telefono, "user", msg.texto)
                await guardar_mensaje(msg.telefono, "assistant", respuesta)

                if calificar_lead(msg.texto) == "alto" or msg.telefono in _leads_activos:
                    _programar_notificacion_lead(msg.telefono, msg.texto)

                await proveedor.enviar_mensaje(msg.telefono, respuesta)

                logger.info(f"Respuesta a {msg.telefono}: {respuesta}")

            return {"status": "ok"}

        except Exception as e:
            logger.error(f"Error en webhook: {e}")
            raise HTTPException(status_code=500, detail=str(e))
