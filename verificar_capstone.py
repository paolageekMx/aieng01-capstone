"""Autoverificación del capstone AIENG01: revisa que las piezas existan (no evalúa su calidad)."""
import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).parent
PLANTILLAS = {"orquestador_sdk.py", "subagentes.py"}   # copias del L6 para leer: no cuentan como tu código
codigo = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in AQUI.rglob("*.py")
                   if ".venv" not in p.parts and p.name not in PLANTILLAS)
readme = (AQUI / "README.md").read_text(encoding="utf-8") if (AQUI / "README.md").exists() else ""
checks = []


def check(nombre, ok, pista):
    checks.append(ok)
    print(f"{'✅' if ok else '❌'} {nombre}" + ("" if ok else f" → {pista}"))


golden = AQUI / "golden_set.json"
casos = json.loads(golden.read_text(encoding="utf-8")).get("casos", []) if golden.exists() else []
L7 = Path("/workshop/aieng01/lab-07-evals-guardrails-trazas/workspace/golden_set.json")   # los 12 casos de PagosYa
del_l7 = {c.get("pregunta") for c in json.loads(L7.read_text(encoding="utf-8")).get("casos", [])} if L7.exists() else set()
propios = [c for c in casos if c.get("pregunta") not in del_l7]

check("README con las 7 secciones", all(s in readme for s in ["## El caso", "## Arquitectura", "## Cómo correrlo",
      "## Evaluación", "## Guardrails", "## Costo", "## Límites"]), "usa la plantilla de la guía")
server = (AQUI / "server.py").read_text(encoding="utf-8") if (AQUI / "server.py").exists() else ""
check("servidor MCP propio", bool(re.search(r"FastMCP|mcp\.server|@\w+\.tool", server))
      and not all(f"def {h}(" in server for h in ("get_case", "search_cases", "create_case")),
      "cambia las herramientas del L4 en server.py por las de tu caso (L3)")
check("Claude Agent SDK", "claude_agent_sdk" in codigo, "el orquestador usa el Agent SDK (L4)")
agente = AQUI / "agente.py"
check("caso propio (ya no es PagosYa)", agente.exists() and "PagosYa" not in agente.read_text(encoding="utf-8"),
      "cambia el SYSTEM (y el docstring) de agente.py a tu caso")
agente_txt = agente.read_text(encoding="utf-8") if agente.exists() else ""
check("subagente cableado", "AgentDefinition" in agente_txt and '"Agent"' in agente_txt,
      'agents=AGENTES y "Agent" en allowed_tools de agente.py (pista del H2)')
check("golden set ≥ 8 casos propios", len(propios) >= 8, f"tiene {len(propios)} tuyos; los 12 del L7 no cuentan")
check("≥ 2 casos adversariales propios", sum("adversarial" in json.dumps(c, ensure_ascii=False).lower() for c in propios) >= 2,
      "marca la categoría de tus casos adversariales")
check("corridas de evals guardadas (antes y después)", len(list((AQUI / "resultados").glob("*.json"))) >= 2
      if (AQUI / "resultados").exists() else False, "python evals.py --etiqueta antes / --etiqueta despues")
check("traza de una pregunta guardada", (AQUI / "resultados" / "traza.txt").exists(),
      "python ver_traza.py > resultados/traza.txt (después de una pregunta adversarial)")
check("guardrails de entrada y salida", "revisar_entrada" in codigo and "revisar_salida" in codigo, "♻ guardrails.py del L7")
check("costo por request registrado", (AQUI / "usage_log.jsonl").exists(), "usa costing.log_usage en cada llamada (L8)")
check("sin API keys en el código", not re.search(r"sk-ant-[A-Za-z0-9]", codigo), "las credenciales van en el entorno")
print(f"\nCAPSTONE: {sum(checks)}/{len(checks)}")
sys.exit(0 if all(checks) else 1)
