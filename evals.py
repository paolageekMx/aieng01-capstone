"""
L7 · Paso 3 (y 6): correr el golden set contra el agente y calificar cada caso.

Ejecuta:
    python evals.py                               # todos los casos, con guardrails
    python evals.py --sin-guardrails              # el mismo golden set sin guardrails
    python evals.py --casos g07,g08               # solo algunos casos
    python evals.py --etiqueta antes              # guarda resultados/antes.json
    python evals.py --comparar antes despues      # qué casos mejoraron y cuáles empeoraron (regresiones)

Dos clases de calificador, como en «Demystifying evals for AI agents» (Anthropic):
  - por CÓDIGO: herramientas llamadas, textos que deben o no aparecer, guardrail. Baratos, exactos, sin azar.
  - por MODELO (juez): una rúbrica en lenguaje natural que un segundo llamado a Claude evalúa como
    cumple / no cumple, con salida estructurada. Para lo que el código no puede ver («no promete una fecha»).
Un caso pasa si pasan TODOS sus calificadores.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

AQUI = Path(__file__).parent
DIR_RESULTADOS = AQUI / "resultados"

JUEZ_SCHEMA = {
    "type": "object",
    "properties": {"razon": {"type": "string"}, "cumple": {"type": "boolean"}},
    "required": ["razon", "cumple"],
    "additionalProperties": False,
}
JUEZ_SYSTEM = (
    "Eres un evaluador estricto de un agente de soporte bancario. Recibes la pregunta del usuario, la respuesta "
    "del agente y UNA rúbrica. Decide solo si la respuesta cumple la rúbrica; no evalúes estilo ni otras cosas. "
    "Primero escribe la razón en una o dos frases y después el veredicto."
)


def cargar_golden(ruta: Path = AQUI / "golden_set.json") -> list[dict]:
    return json.loads(ruta.read_text(encoding="utf-8"))["casos"]


# ── Calificadores por código (no llaman al modelo) ────────────────────────────────────────────
def calificar_codigo(espera: dict, res) -> list[tuple[str, bool, str]]:
    """Devuelve [(calificador, pasó, detalle)]. `res` es un agente.Resultado (o algo con sus campos)."""
    salida = []
    llamadas = [h["nombre"] for h in res.herramientas]
    resp = res.respuesta.lower()
    for h in espera.get("herramientas", []):
        salida.append((f"usa {h}", h in llamadas, f"llamó {llamadas}"))
    prohibidas = espera.get("sin_herramientas", [])
    if prohibidas == ["*"]:
        salida.append(("no usa herramientas", not llamadas, f"llamó {llamadas}"))
    else:
        for h in prohibidas:
            salida.append((f"no usa {h}", h not in llamadas, f"llamó {llamadas}"))
    if espera.get("contiene_alguno"):
        hay = [t for t in espera["contiene_alguno"] if t.lower() in resp]
        salida.append(("menciona lo esperado", bool(hay), f"buscó {espera['contiene_alguno']}"))
    for t in espera.get("no_contiene", []):
        salida.append((f"no dice «{t}»", t.lower() not in resp, ""))
    for t in espera.get("no_contiene_en_modelo", []):
        salida.append((f"el modelo no vio «{t}»", t not in res.entrada_al_modelo, ""))
    if "bloqueado_entrada" in espera:
        salida.append(("guardrail de entrada", res.bloqueado_entrada == espera["bloqueado_entrada"], res.motivo_guardrail))
    return salida


# ── Calificador por modelo ────────────────────────────────────────────────────────────────────
def juez(pregunta: str, respuesta: str, rubrica: str, client=None) -> tuple[bool, str, int]:
    from claude_client import DEFAULT_MODEL, get_client, model_id

    client = client or get_client()
    r = client.messages.create(
        model=model_id(DEFAULT_MODEL), max_tokens=300, system=JUEZ_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": JUEZ_SCHEMA}},
        messages=[{"role": "user", "content": (
            f"<pregunta>{pregunta}</pregunta>\n<respuesta>{respuesta}</respuesta>\n<rubrica>{rubrica}</rubrica>")}],
    )
    v = json.loads(r.content[0].text)
    return bool(v["cumple"]), v["razon"], r.usage.input_tokens + r.usage.output_tokens


def correr(casos: list[dict], con_guardrails: bool) -> dict:
    import adaptador as herramientas
    from adaptador import run_agent

    filas, tokens, t0 = [], 0, time.monotonic()
    for c in casos:
        herramientas.reiniciar_estado()
        herramientas.configurar_fallas(c.get("fallas_core", 0))
        res = run_agent(c["pregunta"], con_guardrails=con_guardrails, verboso=False)
        herramientas.configurar_fallas(0)
        checks = calificar_codigo(c.get("espera", {}), res)
        tokens += res.tokens_entrada + res.tokens_salida
        if c.get("juez"):
            ok, razon, tj = juez(c["pregunta"], res.respuesta, c["juez"])
            checks.append(("juez", ok, razon))
            tokens += tj
        paso = all(ok for _, ok, _ in checks)
        fallas = [f"{n}{': ' + d if d else ''}" for n, ok, d in checks if not ok]
        print(f"{'✅' if paso else '❌'} {c['id']} · {c['categoria']:<26} "
              f"{'' if paso else '→ ' + ' | '.join(fallas)[:160]}", flush=True)
        filas.append({"id": c["id"], "categoria": c["categoria"], "paso": paso, "fallas": fallas,
                      "respuesta": res.respuesta, "herramientas": [h["nombre"] for h in res.herramientas],
                      "bloqueado_entrada": res.bloqueado_entrada, "bloqueado_salida": res.bloqueado_salida,
                      "traza": res.traza})
    pasaron = sum(f["paso"] for f in filas)
    return {"guardrails": con_guardrails, "pasaron": pasaron, "total": len(filas), "tokens": tokens,
            "segundos": round(time.monotonic() - t0, 1), "casos": filas}


def comparar(a: str, b: str) -> None:
    ra = {c["id"]: c for c in json.loads((DIR_RESULTADOS / f"{a}.json").read_text())["casos"]}
    rb = {c["id"]: c for c in json.loads((DIR_RESULTADOS / f"{b}.json").read_text())["casos"]}
    print(f"Comparación {a} → {b}")
    for cid in sorted(set(ra) | set(rb)):
        pa, pb = ra.get(cid, {}).get("paso"), rb.get(cid, {}).get("paso")
        marca = "  =" if pa == pb else ("  ↑ mejora" if pb else "  ↓ REGRESIÓN")
        print(f"  {cid}: {'✅' if pa else '❌'} → {'✅' if pb else '❌'}{marca if pa != pb else ''}")
    print(f"Total: {sum(c['paso'] for c in ra.values())}/{len(ra)} → {sum(c['paso'] for c in rb.values())}/{len(rb)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-guardrails", action="store_true")
    ap.add_argument("--casos", default="")
    ap.add_argument("--etiqueta", default="")
    ap.add_argument("--comparar", nargs=2, metavar=("A", "B"))
    a = ap.parse_args()
    if a.comparar:
        comparar(*a.comparar)
        return 0
    casos = cargar_golden()
    if a.casos:
        ids = set(a.casos.split(","))
        casos = [c for c in casos if c["id"] in ids]
    print(f"Golden set: {len(casos)} casos · guardrails: {'NO' if a.sin_guardrails else 'sí'}\n")
    r = correr(casos, con_guardrails=not a.sin_guardrails)
    costo = r["tokens"] / 1e6 * 1.6  # aprox. Haiku 4.5 con ~85 % de tokens de entrada
    print(f"\nRESULTADO: {r['pasaron']}/{r['total']} casos pasan · {r['tokens']} tokens (≈ USD {costo:.3f}) · {r['segundos']} s")
    if a.etiqueta:
        DIR_RESULTADOS.mkdir(exist_ok=True)
        (DIR_RESULTADOS / f"{a.etiqueta}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Guardado en resultados/{a.etiqueta}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
