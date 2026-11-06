"""
Capstone · SalaYa: el agente de reservas de salas de juntas, con el Claude Agent SDK (♻ agente.py del L4).

Qué cambió respecto al L4: el SYSTEM, el servidor MCP (el nuestro, «salas»), los nombres mcp__salas__…, el
subagente «buscador_alternativas» (L6) y el registro de costo por pregunta (L8). El loop, los permisos, los frenos y el
hook de política son los del L4.

Ejecuta:
    python agente.py "¿Qué salas hay para 6 personas con proyector?"
    MODO_AUDITOR=1 python agente.py "..."     # la política niega reservar
"""

import os
import sys
from pathlib import Path

import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultError,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
    AgentDefinition, #linea agregada
)

from herramientas_locales import servidor_local
from politica import hook_politica
from sdk_config import MODELO, proveedor

AQUI = Path(__file__).parent

SYSTEM = (
    "Eres SalaYa, el asistente de reservas de salas de juntas de la oficina. Usa las herramientas de salas para "
    "buscar salas, consultar agendas y reservar; nunca inventes IDs de sala o de reserva ni digas que una sala está "
    "libre sin consultar su agenda. Si falta la fecha (AAAA-MM-DD), la hora, la duración, el número de personas o el "
    "login del responsable, pídelo. Si una herramienta se niega o falla, lee el motivo y actúa en consecuencia. Solo "
    "atiendes reservas de salas. Responde en español, en máximo 4 frases, y cierra con el siguiente paso."
)

SERVIDORES = {
    # El servidor del L3, como proceso aparte por stdio (el mismo Python del .venv).
    #"casos": {"type": "stdio", "command": sys.executable, "args": [str(AQUI / "server.py")]},
    # Herramientas en este mismo proceso (paso 3).
    #"pagosya": servidor_local,
    "salas": {"type": "stdio", "command": sys.executable, "args": [str(AQUI / "server.py")]},
}

# Mínimo privilegio: `tools=[]` apaga las herramientas de Claude Code (Bash, Read, Edit...) y `allowed_tools`
# aprueba sin preguntar SOLO estas. Nombre de una herramienta MCP en el SDK: mcp__<servidor>__<herramienta>.
HERRAMIENTAS = [
    "mcp__salas__buscar_salas",
    "mcp__salas__consultar_agenda",
    "mcp__salas__reservar",
]


# Subagente (L6): contexto propio, solo lectura. Razón de ser: cuando el horario pedido está ocupado, explora
# varias salas y agendas (muchas llamadas) sin ensuciar el contexto del orquestador, y devuelve solo 3 opciones.
AGENTES = {
    "buscador_alternativas": AgentDefinition(
        description="Úsalo cuando la sala u horario pedidos estén ocupados, para encontrar hasta 3 alternativas libres.",
        prompt=("Eres el buscador de alternativas de SalaYa. Recibes capacidad, fecha, hora y duración. Revisa salas y "
                "agendas SOLO con tus herramientas y devuelve como máximo 3 opciones libres (sala, hora inicio-fin). "
                "No reservas nada ni redactas para el usuario."),
        tools=["mcp__salas__buscar_salas", "mcp__salas__consultar_agenda"],   # SOLO lectura
        model="inherit",
    ),
}

def opciones(**extra) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        agents=AGENTES,
        model=MODELO,
        system_prompt=SYSTEM,
        mcp_servers=SERVIDORES,
        tools=["Agent"],
        allowed_tools=[
            "mcp__salas__buscar_salas",
            "mcp__salas__consultar_agenda",
            "mcp__salas__reservar",
            "Agent",
        ],
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[hook_politica])]},
        setting_sources=[],                                     # aislado: no lee ~/.claude ni .claude/ del proyecto
        max_turns=int(os.environ.get("MAX_TURNOS", "10")),      # freno 1: vueltas
        max_budget_usd=float(os.environ.get("PRESUPUESTO_USD", "0.25")),  # freno 2: costo
        cwd=str(AQUI),
        **extra,
    )


def mostrar(m) -> None:
    """La traza: qué herramienta pidió el modelo, cómo salió y, al final, turnos y costo."""
    if isinstance(m, AssistantMessage):
        for b in m.content:
            if isinstance(b, ToolUseBlock):
                print(f"  [tool] {b.name}({b.input})", flush=True)
            elif isinstance(b, TextBlock) and b.text.strip():
                print(f"\nAgente: {b.text.strip()}", flush=True)
    elif isinstance(m, UserMessage) and isinstance(m.content, list):
        for b in m.content:
            if isinstance(b, ToolResultBlock):
                if b.is_error:
                    print(f"    → error: {str(b.content)[:500]}", flush=True)
                else:
                    print("    → ok", flush=True)
    elif isinstance(m, ResultMessage):
        costo = f"USD {m.total_cost_usd:.4f}" if m.total_cost_usd is not None else "s/d"
        print(f"\n[resultado] {m.subtype} · turnos={m.num_turns} · costo≈{costo} · {m.duration_ms / 1000:.1f}s", flush=True)


async def correr(mision: str) -> None:
    try:
        async for m in query(prompt=mision, options=opciones()):
            mostrar(m)
    except ResultError as exc:
        # Cuando un freno corta (max_turns, max_budget_usd), el SDK entrega el ResultMessage con ese subtype
        # y ADEMÁS termina con ResultError. Es el freno funcionando: se reporta, no se muestra una traza.
        print(f"[freno] {exc}", flush=True)


if __name__ == "__main__":
    mision = " ".join(sys.argv[1:]) or "¿Qué salas hay para 6 personas con proyector"
    print("=" * 70)
    print(f"  Misión: {mision}")
    print(f"  {proveedor()} · {MODELO}{' · MODO AUDITOR' if os.environ.get('MODO_AUDITOR') == '1' else ''}")
    print("=" * 70)
    anyio.run(correr, mision)


