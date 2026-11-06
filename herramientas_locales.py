"""
L4 · Paso 3: una herramienta EN PROCESO (sin servidor aparte).

`@tool` + `create_sdk_mcp_server` convierten una función async de este mismo programa en un servidor MCP
que el SDK monta en memoria. Úsalo para lógica propia del agente; usa un servidor MCP aparte (como el del
L3) para un sistema que comparten varios agentes.
"""

import json

from claude_agent_sdk import create_sdk_mcp_server, tool


def reembolso(monto_cop: float, dias_desde_cobro: int) -> dict:
    """Política de reembolsos de PagosYa (lógica pura, se prueba sin modelo).

    Hasta 30 días: 100 %. De 31 a 60: 50 %. Más de 60: no hay reembolso automático (lo decide una persona).
    """
    if monto_cop <= 0 or dias_desde_cobro < 0:
        raise ValueError("el monto debe ser positivo y los días no pueden ser negativos")
    porcentaje = 100 if dias_desde_cobro <= 30 else 50 if dias_desde_cobro <= 60 else 0
    return {"porcentaje": porcentaje, "monto_reembolso_cop": round(monto_cop * porcentaje / 100),
            "requiere_persona": porcentaje == 0}


@tool(
    "calcular_reembolso",
    "Calcula cuánto se le reembolsa a un cliente por un cobro, según la política de PagosYa. "
    "Úsala antes de prometerle un monto al cliente. monto_cop en pesos; dias_desde_cobro: días desde el cargo.",
    {"monto_cop": float, "dias_desde_cobro": int},
)
async def calcular_reembolso(args: dict) -> dict:
    try:
        r = reembolso(float(args["monto_cop"]), int(args["dias_desde_cobro"]))
        return {"content": [{"type": "text", "text": json.dumps(r, ensure_ascii=False)}]}
    except (KeyError, ValueError) as exc:  # error accionable, como en el L2: el modelo lo lee y corrige
        return {"content": [{"type": "text", "text": f"Entrada inválida: {exc}. Pide el dato al usuario."}], "is_error": True}


servidor_local = create_sdk_mcp_server(name="pagosya", version="1.0.0", tools=[calcular_reembolso])
