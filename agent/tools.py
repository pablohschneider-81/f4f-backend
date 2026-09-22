# agent/tools.py — Herramientas del agente F4F Assistant
# Generado por AgentKit

"""
Herramientas específicas de Fittest4Fit. NOTA: agent/brain.py es puramente
conversacional (system prompt + historial); estas funciones quedan listas
para usarse más adelante (por ejemplo con tool-calling de Claude), no se
invocan automáticamente en cada mensaje todavía.
"""

import os
import yaml
import logging

from agent.memory import guardar_lead, guardar_solicitud_mentoria

logger = logging.getLogger("agentkit")


def cargar_info_negocio() -> dict:
    """Carga la información del negocio desde business.yaml."""
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


def obtener_horario() -> dict:
    """Retorna el horario de atención del negocio."""
    info = cargar_info_negocio()
    return {
        "horario": info.get("negocio", {}).get("horario", "No disponible"),
        "esta_abierto": True,  # TODO: calcular según hora actual y horario
    }


def buscar_en_knowledge(consulta: str) -> str:
    """Busca información relevante en los archivos de /knowledge."""
    resultados = []
    knowledge_dir = "knowledge"

    if not os.path.exists(knowledge_dir):
        return "No hay archivos de conocimiento disponibles."

    for archivo in os.listdir(knowledge_dir):
        ruta = os.path.join(knowledge_dir, archivo)
        if archivo.startswith(".") or not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
                if consulta.lower() in contenido.lower():
                    resultados.append(f"[{archivo}]: {contenido[:500]}")
        except (UnicodeDecodeError, IOError):
            continue

    if resultados:
        return "\n---\n".join(resultados)
    return "No encontré información específica sobre eso en mis archivos."


async def registrar_lead(telefono: str, nombre: str | None, interes: str | None):
    """Registra un lead calificado (interés real en un programa)."""
    await guardar_lead(telefono, nombre, interes)
    logger.info(f"Lead registrado: {telefono} — interés: {interes}")


def calificar_lead(mensaje: str) -> str:
    """Heurística simple para calificar el nivel de interés. Retorna alto/medio/bajo."""
    texto = mensaje.lower()
    señales_alto = [
        "quiero anotarme", "cómo pago", "como pago", "quiero empezar", "quiero comprar", "me interesa",
        "quiero agendar", "quiero una mentoría", "quiero una mentoria", "quiero reservar",
        "mi disponibilidad", "mi email es", "mi correo es", "mi teléfono es", "mi telefono es",
        "@gmail", "@hotmail", "@outlook", "@yahoo",
    ]
    señales_medio = ["cuánto cuesta", "cuanto cuesta", "precio", "info", "información", "informacion"]

    if any(s in texto for s in señales_alto):
        return "alto"
    if any(s in texto for s in señales_medio):
        return "medio"
    return "bajo"


async def solicitar_mentoria(
    telefono: str, nombre: str | None, disponibilidad: str | None, motivo: str | None
) -> int:
    """
    Registra una solicitud de mentoría/consulta. Sin calendario conectado
    todavía, queda como cola de solicitudes que Hernán confirma manualmente
    (ver listar_solicitudes_pendientes() en agent/memory.py).
    """
    solicitud_id = await guardar_solicitud_mentoria(telefono, nombre, disponibilidad, motivo)
    logger.info(f"Solicitud de mentoría #{solicitud_id} registrada para {telefono}")
    return solicitud_id
