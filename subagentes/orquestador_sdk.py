"""
L6 · Paso 5: la misma orquestación con el Claude Agent SDK.

Lo que en orquestador.py escribiste a mano (la herramienta delegar, el loop de cada subagente, el paralelo),
el SDK lo trae con `agents=`: defines cada subagente con su descripción, su prompt y sus herramientas, y el
agente principal los invoca con su herramienta «Agent». Cada subagente corre en su propio contexto.

Ejecuta: python orquestador_sdk.py
"""

from __future__ import annotations

import json
import sys

import anyio
from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultError,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

from herramientas import IMPLS
from orquestador import RECLAMO
from sdk_config import MODELO, proveedor
from subagentes import SUBAGENTES


def _envolver(nombre: str):
    """Convierte una función de herramientas.py en una herramienta MCP en proceso."""
    schema = {"consultar_movimientos": {"cliente": str}, "consultar_casos": {"cliente": str},
              "buscar_politicas": {"consulta": str}}[nombre]

    @tool(nombre, IMPLS[nombre].__doc__ or nombre.replace("_", " "), schema)
    async def _h(args: dict) -> dict:
        try:
            return {"content": [{"type": "text", "text": json.dumps(IMPLS[nombre](**args), ensure_ascii=False)}]}
        except (LookupError, TypeError, ValueError) as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}
    return _h


DATOS = create_sdk_mcp_server("pagosya", tools=[_envolver(n) for n in IMPLS])


def mcp(nombre: str) -> str:
    return f"mcp__pagosya__{nombre}"


AGENTES = {
    nombre: AgentDefinition(
        description=cfg["descripcion"],
        prompt=cfg["system"],
        tools=[mcp(h) for h in cfg["herramientas"]],   # cada subagente, SOLO sus herramientas
        model="inherit",
    )
    for nombre, cfg in SUBAGENTES.items()
}

SYSTEM = (
    "Eres el orquestador de reclamos complejos de PagosYa. No consultas datos ni políticas tú mismo: delega en los "
    "subagentes investigador_cuenta y experto_politicas con tareas autocontenidas, las dos a la vez si son "
    "independientes. Con sus informes escribe un DICTAMEN con «Qué pasó», «Qué dice la política» (con fuentes) y "
    "«Acciones recomendadas». Responde en español."
)


async def solo_subagentes(input_data: dict, tool_use_id, context) -> dict:
    """PreToolUse: las herramientas de datos son de los subagentes; el orquestador solo delega."""
    nombre = input_data.get("tool_name", "")
    if nombre.startswith("mcp__pagosya__") and not input_data.get("agent_id"):
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": "Tú no consultas datos: delega en el subagente que corresponde."}}
    return {}


def opciones() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=MODELO,
        system_prompt=SYSTEM,
        mcp_servers={"pagosya": DATOS},
        agents=AGENTES,
        tools=["Agent"],                                            # el principal solo puede delegar
        allowed_tools=["Agent"] + [mcp(n) for n in IMPLS],
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[solo_subagentes])]},
        setting_sources=[],
        max_turns=12,
        max_budget_usd=0.50,
    )


async def main(reclamo: str) -> None:
    print(f"{proveedor()} · {MODELO}\n" + "=" * 70)
    try:
        await _correr(reclamo)
    except ResultError as exc:  # un freno (max_turns, max_budget_usd) cortó la corrida: se reporta, sin traza
        print(f"[freno] {exc}", flush=True)


async def _correr(reclamo: str) -> None:
    async for m in query(prompt=reclamo, options=opciones()):
        quien = "subagente" if getattr(m, "parent_tool_use_id", None) else "orquestador"
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, ToolUseBlock):
                    detalle = b.input.get("subagent_type") or b.input.get("description") or ""
                    print(f"  [{quien}] [tool] {b.name} {detalle}".rstrip(), flush=True)
                elif isinstance(b, TextBlock) and b.text.strip() and quien == "orquestador":
                    print(f"\nDICTAMEN:\n{b.text.strip()}", flush=True)
        elif isinstance(m, ResultMessage):
            costo = f"USD {m.total_cost_usd:.4f}" if m.total_cost_usd is not None else "s/d"
            print(f"\n[resultado] {m.subtype} · turnos={m.num_turns} · costo≈{costo} · {m.duration_ms / 1000:.1f}s")


if __name__ == "__main__":
    anyio.run(main, " ".join(sys.argv[1:]) or RECLAMO)
