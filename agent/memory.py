# agent/memory.py — Memoria de conversaciones con SQLite
# Generado por AgentKit

"""
Sistema de memoria del agente. Guarda el historial de conversaciones
(por teléfono en WhatsApp, o por session_id del widget web) usando
SQLite (local/gratis) o PostgreSQL (producción).
"""

import os
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, select, Integer
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./agentkit.db")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Mensaje(Base):
    """Modelo de mensaje en la base de datos."""
    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(200), index=True)  # teléfono o "web:<session_id>"
    role: Mapped[str] = mapped_column(String(20))  # "user" o "assistant"
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Lead(Base):
    """Lead calificado por el agente (interés en un programa)."""
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(200), index=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=True)
    interes: Mapped[str] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SolicitudMentoria(Base):
    """Solicitud de mentoría/consulta pendiente de confirmar por Hernán."""
    __tablename__ = "solicitudes_mentoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(200), index=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=True)
    disponibilidad: Mapped[str] = mapped_column(Text, nullable=True)
    motivo: Mapped[str] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def inicializar_db():
    """Crea las tablas si no existen."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def guardar_mensaje(telefono: str, role: str, content: str):
    """Guarda un mensaje en el historial de conversación."""
    async with async_session() as session:
        mensaje = Mensaje(telefono=telefono, role=role, content=content, timestamp=datetime.utcnow())
        session.add(mensaje)
        await session.commit()


async def obtener_historial(telefono: str, limite: int = 20) -> list[dict]:
    """Recupera los últimos N mensajes de una conversación."""
    async with async_session() as session:
        query = (
            select(Mensaje)
            .where(Mensaje.telefono == telefono)
            .order_by(Mensaje.timestamp.desc())
            .limit(limite)
        )
        result = await session.execute(query)
        mensajes = result.scalars().all()
        mensajes.reverse()
        return [{"role": msg.role, "content": msg.content} for msg in mensajes]


async def limpiar_historial(telefono: str):
    """Borra todo el historial de una conversación."""
    async with async_session() as session:
        query = select(Mensaje).where(Mensaje.telefono == telefono)
        result = await session.execute(query)
        for msg in result.scalars().all():
            session.delete(msg)
        await session.commit()


async def guardar_lead(telefono: str, nombre: str | None, interes: str | None):
    """Registra un lead calificado por el agente."""
    async with async_session() as session:
        session.add(Lead(telefono=telefono, nombre=nombre, interes=interes))
        await session.commit()


async def guardar_solicitud_mentoria(
    telefono: str, nombre: str | None, disponibilidad: str | None, motivo: str | None
) -> int:
    """Registra una solicitud de mentoría pendiente de confirmar. Retorna el id."""
    async with async_session() as session:
        solicitud = SolicitudMentoria(
            telefono=telefono, nombre=nombre, disponibilidad=disponibilidad, motivo=motivo
        )
        session.add(solicitud)
        await session.commit()
        await session.refresh(solicitud)
        return solicitud.id


async def listar_solicitudes_pendientes() -> list[dict]:
    """Lista las solicitudes de mentoría que Hernán todavía no confirmó."""
    async with async_session() as session:
        query = (
            select(SolicitudMentoria)
            .where(SolicitudMentoria.estado == "pendiente")
            .order_by(SolicitudMentoria.timestamp.asc())
        )
        result = await session.execute(query)
        return [
            {
                "id": s.id, "telefono": s.telefono, "nombre": s.nombre,
                "disponibilidad": s.disponibilidad, "motivo": s.motivo,
                "timestamp": s.timestamp.isoformat(),
            }
            for s in result.scalars().all()
        ]
