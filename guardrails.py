"""
L7 · Pasos 4 y 5: guardrails de entrada y de salida del agente de PagosYa.

Un guardrail es código determinista que corre ANTES (entrada) o DESPUÉS (salida) del modelo y que
puede dejar pasar, corregir o bloquear. No reemplaza al system prompt: lo respalda. El prompt le PIDE
al modelo que no invente un número de caso; el guardrail de salida COMPRUEBA que no lo haya hecho.

    Entrada (paso 4)                               Salida (paso 5)
    ─ inyección de instrucciones → bloquear        ─ ids (CASO-…, T-…) que ninguna herramienta
    ─ PII que el modelo no necesita → enmascarar      devolvió → reemplazar por respuesta segura
      (tarjetas, claves) antes de mandarla         ─ promesas que el negocio no puede cumplir
                                                     → reemplazar por respuesta segura

Todo aquí es barato (regex, sin modelo) y corre en milisegundos. Un guardrail con LLM (un clasificador)
es la siguiente capa, cuando las reglas no alcanzan; se ve en las slides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Decision:
    permitir: bool
    texto: str                      # el texto que sigue (saneado o reemplazado)
    motivo: str = ""
    hallazgos: list[str] = field(default_factory=list)


RESPUESTA_BLOQUEO_ENTRADA = (
    "Solo puedo ayudarte con consultas sobre tu propia cuenta de PagosYa: transferencias, pagos y casos de "
    "soporte. Si necesitas otra cosa, escríbenos por los canales oficiales."
)
RESPUESTA_SEGURA_SALIDA = (
    "No pude confirmar esa información con los sistemas de PagosYa y prefiero no darte un dato equivocado. "
    "Puedo abrir un caso para que una persona lo revise. ¿Quieres que lo haga?"
)

# ── Entrada ───────────────────────────────────────────────────────────────────────────────────
PATRONES_INYECCION = [
    r"ignora\w*\s+(todas?\s+)?(las\s+|tus\s+)?(instrucciones|reglas|indicaciones)",
    r"olvida\w*\s+(todas?\s+)?(las\s+|tus\s+)?(instrucciones|reglas)",
    r"(system|sistema)\s*prompt",
    r"(modo|mode)\s+(desarrollador|developer|dios|admin)",
    r"ahora\s+eres\s+",
    r"(todos|todas)\s+los\s+clientes",
]

# Tarjeta: 13 a 19 dígitos, que pueden venir separados por espacios o guiones (4111 1111 1111 1111).
# El documento de identidad (6 a 10 dígitos seguidos) NO es tarjeta: el agente lo necesita.
RE_TARJETA = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
# Clave, contraseña o PIN seguidos de su valor: «mi clave es 4321», «contraseña: hola123», «PIN 0000».
RE_CLAVE = re.compile(r"\b(clave|contraseña|pin)\b(\s+es|\s*:)?\s+([^\s.,;]+)", re.IGNORECASE)


def detectar_inyeccion(texto: str) -> str | None:
    """Devuelve el patrón que coincidió, o None. Reglas, no un modelo: barato, explicable y con falsos
    negativos conocidos (una inyección bien escrita pasa). Por eso hay también guardrail de salida."""
    t = texto.lower()
    for p in PATRONES_INYECCION:
        if re.search(p, t):
            return p
    return None


def enmascarar_pii(texto: str) -> tuple[str, list[str]]:
    """Reemplaza la PII que el agente NO necesita antes de que llegue al modelo (y a las trazas).

    TODO (paso 4): hoy devuelve el texto sin tocar. Implementa:
      1. Cada coincidencia de RE_TARJETA se reemplaza por «[TARJETA]» y se agrega "tarjeta" a hallazgos.
      2. Cada coincidencia de RE_CLAVE conserva la palabra («clave», «PIN», …) y reemplaza solo el valor:
         «mi clave es 4321» → «mi clave [OCULTA]». Se agrega "clave" a hallazgos.
      3. El documento (6 a 10 dígitos seguidos) NO se toca.
    Devuelve (texto_saneado, hallazgos).

    Pista: `RE_TARJETA.subn("[TARJETA]", texto)` devuelve (texto_nuevo, cuántas); para la clave,
    `RE_CLAVE.subn(lambda m: f"{m.group(1)} [OCULTA]", texto)`.
    """
    hallazgos = []
    texto, n = RE_TARJETA.subn("[TARJETA]", texto)
    if n:
        hallazgos.append("tarjeta")
    texto, n = RE_CLAVE.subn(lambda m: f"{m.group(1)} [OCULTA]", texto)
    if n:
        hallazgos.append("clave")
    return texto, hallazgos


def revisar_entrada(texto: str) -> Decision:
    patron = detectar_inyeccion(texto)
    if patron:
        return Decision(False, RESPUESTA_BLOQUEO_ENTRADA, f"posible inyección de instrucciones ({patron})", ["inyeccion"])
    saneado, hallazgos = enmascarar_pii(texto)
    return Decision(True, saneado, "pii enmascarada" if hallazgos else "", hallazgos)


# ── Salida ────────────────────────────────────────────────────────────────────────────────────
RE_IDS = re.compile(r"\b(?:CASO-\d+|T-\d+)\b")
PROMESAS_PROHIBIDAS = ["te garantizo", "te prometo", "garantizamos", "con total seguridad", "es seguro que mañana"]


def ids_no_respaldados(respuesta: str, evidencia: str) -> list[str]:
    """Los identificadores (CASO-…, T-…) que la respuesta menciona y que NO aparecen en la evidencia: todo lo que
    devolvieron las herramientas en esta conversación más lo que escribió el usuario (un id que el usuario dio no es
    inventado; repetirlo está bien).

    TODO (paso 5): hoy devuelve siempre []. Implementa:
      1. Encuentra todos los ids de la respuesta con RE_IDS.
      2. Devuelve los que no estén en `evidencia`, sin repetir y en el orden en que aparecen.

    Pista: `for i in RE_IDS.findall(respuesta)`, y `if i not in evidencia and i not in salida`.
    """
    salida = []
    for i in RE_IDS.findall(respuesta):
        if i not in evidencia and i not in salida:
            salida.append(i)
    return salida


def promesas_prohibidas(respuesta: str) -> list[str]:
    """Frases de promesa que el negocio no puede cumplir. Ignora las negadas («no te prometo…»): una regla
    que no mira eso bloquea justo la respuesta prudente (falso positivo), y eso también se mide en los evals."""
    t = respuesta.lower()
    encontradas = []
    for p in PROMESAS_PROHIBIDAS:
        for m in re.finditer(re.escape(p), t):
            if not re.search(r"\bno\s+(\w+\s+)?$", t[max(0, m.start() - 14):m.start()]):
                encontradas.append(p)
                break
    return encontradas


def revisar_salida(respuesta: str, evidencia: str) -> Decision:
    hallazgos = []
    sin_respaldo = ids_no_respaldados(respuesta, evidencia)
    if sin_respaldo:
        hallazgos.append(f"ids sin respaldo: {sin_respaldo}")
    promesas = promesas_prohibidas(respuesta)
    if promesas:
        hallazgos.append(f"promesas: {promesas}")
    if RE_TARJETA.search(respuesta):
        hallazgos.append("tarjeta en la respuesta")
    if hallazgos:
        return Decision(False, RESPUESTA_SEGURA_SALIDA, "; ".join(hallazgos), hallazgos)
    return Decision(True, respuesta)
