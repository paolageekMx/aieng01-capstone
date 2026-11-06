"""
L6 · Los dos subagentes especializados.

Un subagente es una ventana de contexto LIMPIA con un rol, unas herramientas y un formato de entrega.
Recibe una tarea acotada del orquestador, trabaja en su propio contexto (sus búsquedas no ensucian el del
orquestador) y devuelve un informe corto.

Pruébalo solo:
    python subagentes.py investigador_cuenta "Revisa cargos duplicados y transferencias retenidas de laura.gomez"
"""

from __future__ import annotations

import json
import sys

from claude_client import DEFAULT_MODEL, get_client, model_id
from herramientas import SCHEMAS, ejecutar

FORMATO = ("Entrega un informe de máximo 6 viñetas con HECHOS verificados (IDs, fechas, montos, fuentes). "
           "Si algo no lo pudiste verificar, dilo. No recomiendes acciones: eso lo decide el orquestador.")

SUBAGENTES = {
    "investigador_cuenta": {
        "descripcion": "Investiga los datos de un cliente: movimientos (cargos, transferencias) y casos de soporte.",
        "system": ("Eres el investigador de cuentas de PagosYa. Solo consultas datos del cliente con tus herramientas; "
                   "no conoces las políticas. " + FORMATO),
        "herramientas": ["consultar_movimientos", "consultar_casos"],
    },
    "experto_politicas": {
        "descripcion": "Encuentra y cita las políticas oficiales de PagosYa que aplican a una situación.",
        "system": ("Eres el experto en políticas de PagosYa. Solo buscas en las políticas oficiales y citas cada regla "
                   "con su fuente [archivo#sección]; no conoces los datos de ningún cliente. " + FORMATO),
        "herramientas": ["buscar_politicas"],
    },
}


def correr_subagente(nombre: str, tarea: str, max_vueltas: int = 6) -> dict:
    """Corre el loop del subagente en su propio contexto. Devuelve informe, tokens y vueltas."""
    cfg = SUBAGENTES[nombre]
    client = get_client().with_options(max_retries=4, timeout=60)
    tools = [SCHEMAS[h] for h in cfg["herramientas"]]
    mensajes = [{"role": "user", "content": tarea}]
    tokens = 0
    for vuelta in range(1, max_vueltas + 1):
        r = client.messages.create(model=model_id(DEFAULT_MODEL), max_tokens=800, system=cfg["system"],
                                   tools=tools, messages=mensajes)
        tokens += r.usage.input_tokens + r.usage.output_tokens
        if r.stop_reason != "tool_use":
            informe = "".join(b.text for b in r.content if b.type == "text")
            print(f"    [{nombre}] terminó en {vuelta} vueltas · {tokens} tokens", flush=True)
            return {"subagente": nombre, "informe": informe, "tokens": tokens, "vueltas": vuelta}
        mensajes.append({"role": "assistant", "content": r.content})
        resultados = []
        for b in r.content:
            if b.type == "tool_use":
                print(f"    [{nombre}] [tool] {b.name}({json.dumps(b.input, ensure_ascii=False)})", flush=True)
                resultados.append({"type": "tool_result", "tool_use_id": b.id, **ejecutar(b.name, b.input)})
        mensajes.append({"role": "user", "content": resultados})
    return {"subagente": nombre, "informe": "[freno] no terminó a tiempo", "tokens": tokens, "vueltas": max_vueltas}


if __name__ == "__main__":
    nombre, tarea = sys.argv[1], " ".join(sys.argv[2:])
    print(correr_subagente(nombre, tarea)["informe"])
