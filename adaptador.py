"""Adaptador: corre tu agente del Claude Agent SDK (el del L4) con la interfaz que espera evals.py del L7.

evals.py del L7 se escribió para el agente con loop propio, que devuelve un Resultado. Este módulo da esa
misma interfaz sobre el SDK, sin tocar agente.py: en evals.py cambias dos líneas
    import herramientas                → import adaptador as herramientas
    from agente import run_agent       → from adaptador import run_agent
"""
from dataclasses import dataclass, field

import anyio
from claude_agent_sdk import (AssistantMessage, ResultError, ResultMessage, TextBlock, ToolResultBlock,
                              ToolUseBlock, UserMessage, query)

from agente import opciones                      # el mismo agente del L4 (o tu capstone)
from guardrails import revisar_entrada, revisar_salida


@dataclass
class Resultado:                                 # los campos que lee evals.py
    pregunta: str
    respuesta: str = ""
    entrada_al_modelo: str = ""
    herramientas: list = field(default_factory=list)
    evidencia: str = ""
    bloqueado_entrada: bool = False
    bloqueado_salida: bool = False
    motivo_guardrail: str = ""
    tokens_entrada: int = 0
    tokens_salida: int = 0
    traza: str = ""


def reiniciar_estado():                          # evals.py los llama antes de cada caso; con tu servidor MCP
    pass                                         # no hacen nada (si tus datos cambian, reinícialos aquí)


def configurar_fallas(n=0):
    pass


async def _correr(res: Resultado) -> None:
    textos, evidencia = [], []
    try:
        async for m in query(prompt=res.entrada_al_modelo, options=opciones()):
            if isinstance(m, AssistantMessage):
                for b in m.content:
                    if isinstance(b, ToolUseBlock):      # mcp__casos__get_case → get_case
                        res.herramientas.append({"nombre": b.name.split("__")[-1], "entrada": b.input})
                    elif isinstance(b, TextBlock) and b.text.strip():
                        textos.append(b.text.strip())
            elif isinstance(m, UserMessage) and isinstance(m.content, list):
                evidencia += [str(b.content) for b in m.content if isinstance(b, ToolResultBlock)]
            elif isinstance(m, ResultMessage):
                u = m.usage or {}
                res.tokens_entrada = sum(u.get(k, 0) or 0 for k in ("input_tokens", "cache_read_input_tokens",
                                                                   "cache_creation_input_tokens"))
                res.tokens_salida = u.get("output_tokens", 0) or 0
                if m.result:
                    textos.append(m.result.strip())
    except ResultError as exc:                   # un freno (max_turns, max_budget_usd) cortó la corrida
        textos.append(f"[freno] {exc}")
    res.respuesta = textos[-1] if textos else ""
    res.evidencia = "\n".join(evidencia)


def run_agent(pregunta: str, con_guardrails: bool = True, verboso: bool = False) -> Resultado:
    res = Resultado(pregunta=pregunta, entrada_al_modelo=pregunta)
    if con_guardrails:
        d = revisar_entrada(pregunta)
        if not d.permitir:                       # bloqueado: el modelo ni se entera
            res.respuesta, res.bloqueado_entrada, res.motivo_guardrail = d.texto, True, d.motivo
            return res
        res.entrada_al_modelo = d.texto          # con la PII enmascarada
    anyio.run(_correr, res)
    if con_guardrails:
        d = revisar_salida(res.respuesta, pregunta + "\n" + res.evidencia)
        if not d.permitir:
            res.respuesta, res.bloqueado_salida, res.motivo_guardrail = d.texto, True, d.motivo
    return res
