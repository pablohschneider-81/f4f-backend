# agent/brain.py — Cerebro del agente: conexión con Gemini (Google, capa gratis)
# Generado por AgentKit

"""
Lógica de IA del agente. Lee el system prompt de prompts.yaml
y genera respuestas usando la API de Google Gemini (gratis dentro
de los límites de uso de Google AI Studio).
"""

import os
import asyncio
import yaml
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")


def cargar_config_prompts() -> dict:
    """Lee toda la configuración desde config/prompts.yaml."""
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def cargar_system_prompt() -> str:
    """Lee el system prompt desde config/prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("system_prompt", "Eres un asistente útil. Responde en español.")


def obtener_mensaje_error() -> str:
    """Retorna el mensaje de error configurado en prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("error_message", "Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo en unos minutos.")


def obtener_mensaje_fallback() -> str:
    """Retorna el mensaje de fallback configurado en prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("fallback_message", "Disculpa, no entendí tu mensaje. ¿Podrías reformularlo?")


async def generar_respuesta(mensaje: str, historial: list[dict]) -> str:
    """
    Genera una respuesta usando Gemini.

    Args:
        mensaje: El mensaje nuevo del usuario
        historial: Lista de mensajes anteriores [{"role": "user/assistant", "content": "..."}]

    Returns:
        La respuesta generada por Gemini
    """
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback()

    system_prompt = cargar_system_prompt()

    # Gemini usa "user"/"model" como roles (no "assistant")
    contenidos = []
    for msg in historial:
        rol = "model" if msg["role"] == "assistant" else "user"
        contenidos.append(types.Content(role=rol, parts=[types.Part(text=msg["content"])]))

    contenidos.append(types.Content(role="user", parts=[types.Part(text=mensaje)]))

    # Reintentamos ante CUALQUIER error transitorio: alta demanda de Gemini
    # (503/429), o problemas de red al primer llamado después de que el
    # servidor gratuito de Render estuvo "dormido" (arranque en frío). Solo
    # nos rendimos después de agotar los intentos.
    intentos = 3
    for intento in range(1, intentos + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=contenidos,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=1024,
                ),
            )

            respuesta = (response.text or "").strip()
            if not respuesta:
                logger.warning("Gemini devolvió una respuesta vacía")
                if intento < intentos:
                    await asyncio.sleep(intento * 1.5)
                    continue
                return obtener_mensaje_error()

            logger.info(f"Respuesta generada con Gemini (intento {intento}/{intentos})")
            return respuesta

        except Exception as e:
            logger.warning(f"Error de Gemini (intento {intento}/{intentos}): {e}")
            if intento < intentos:
                await asyncio.sleep(intento * 1.5)
                continue
            logger.error(f"Error Gemini API tras {intentos} intentos: {e}")
            return obtener_mensaje_error()
