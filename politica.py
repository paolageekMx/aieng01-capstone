"""
L4 · Paso 4: la política del agente, aplicada con un HOOK antes de cada herramienta.

El modelo decide QUÉ herramienta usar; la política decide si PUEDE. El hook PreToolUse corre en tu código
antes de que la herramienta se ejecute, y su decisión no depende de que el modelo «se porte bien».

`decidir()` es lógica pura (verificar.py la prueba sin modelo). `hook_politica()` la conecta al SDK.
"""

import os

ESCRITURA = {"create_case", "add_note", "escalate_case"}
PREFIJO = "mcp__casos__"


def decidir(herramienta: str, entrada: dict, modo_auditor: bool) -> tuple[bool, str]:
    """Decide si el agente puede ejecutar `herramienta` (nombre SIN el prefijo mcp__casos__) con `entrada`.

    Devuelve (permitido, razón). La razón la lee el MODELO cuando se le niega algo: que diga qué hacer.

    Reglas (TODO paso 4):
      1. En modo auditor, ninguna herramienta de ESCRITURA: niega con una razón que le diga al modelo que
         solo puede leer y que recomiende la acción al usuario en lugar de ejecutarla.
      2. escalate_case exige un motivo de al menos 20 caracteres (sin contar espacios al inicio y al final):
         si no, niega y explica que debe justificar por qué escalar.
      3. Todo lo demás se permite: (True, "").
    """
    if modo_auditor and herramienta in ESCRITURA:
        return False, ("Modo auditor: este agente solo puede leer. No ejecutes la acción: explícale al usuario "
                       "qué harías y por qué, para que lo apruebe una persona.")
    if herramienta == "escalate_case" and len(entrada.get("motivo", "").strip()) < 20:
        return False, ("Para escalar hay que justificarlo: vuelve a llamar con un motivo de al menos 20 caracteres "
                       "que diga por qué (días sin avance, riesgo de que el cliente se vaya, monto).")
    return True, ""


async def hook_politica(input_data: dict, tool_use_id: str | None, context) -> dict:
    """PreToolUse: se llama antes de CADA herramienta. Devolver {} = seguir; devolver «deny» = frenarla."""
    nombre = input_data.get("tool_name", "")
    if not nombre.startswith(PREFIJO):
        return {}
    modo_auditor = os.environ.get("MODO_AUDITOR") == "1"
    permitido, razon = decidir(nombre.removeprefix(PREFIJO), input_data.get("tool_input", {}), modo_auditor)
    if permitido:
        return {}
    print(f"  [política] ✋ {nombre.removeprefix(PREFIJO)} denegada: {razon}", flush=True)
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": razon}}
