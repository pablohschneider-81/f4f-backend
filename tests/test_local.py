# tests/test_local.py — Simulador de chat en terminal (opcional, requiere terminal)
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial, limpiar_historial

TELEFONO_TEST = "test-local-001"


async def main():
    await inicializar_db()
    print("\n" + "=" * 55)
    print("   F4F Assistant — Test Local")
    print("=" * 55 + "\n")
    print("  Escribí mensajes como si fueras un cliente.")
    print("  'limpiar' borra el historial, 'salir' termina.\n")
    print("-" * 55 + "\n")

    while True:
        try:
            mensaje = input("Tu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nTest finalizado.")
            break

        if not mensaje:
            continue
        if mensaje.lower() == "salir":
            print("\nTest finalizado.")
            break
        if mensaje.lower() == "limpiar":
            await limpiar_historial(TELEFONO_TEST)
            print("[Historial borrado]\n")
            continue

        historial = await obtener_historial(TELEFONO_TEST)
        print("\nAgente: ", end="", flush=True)
        respuesta = await generar_respuesta(mensaje, historial)
        print(respuesta + "\n")

        await guardar_mensaje(TELEFONO_TEST, "user", mensaje)
        await guardar_mensaje(TELEFONO_TEST, "assistant", respuesta)


if __name__ == "__main__":
    asyncio.run(main())
