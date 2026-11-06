"""
L7 · Paso 2: leer una traza como la leería quien atiende un incidente.

Ejecuta:
    python ver_traza.py                      # la última traza
    python ver_traza.py trazas/<id>.jsonl    # una traza concreta
"""

import sys
from pathlib import Path

import trazas

# Haiku 4.5, USD por millón de tokens
PRECIO_ENTRADA, PRECIO_SALIDA = 1.0, 5.0


def mostrar(ruta: Path) -> None:
    eventos = trazas.leer(ruta)
    tin = sum(e.get("gen_ai.usage.input_tokens", 0) for e in eventos)
    tout = sum(e.get("gen_ai.usage.output_tokens", 0) for e in eventos)
    print(f"Traza {eventos[0]['traza_id']} · {ruta.name}")
    print(f"Pregunta: {eventos[0].get('pregunta', '')}\n")
    for e in eventos:
        t = f"{e['t_ms']:>8.0f} ms"
        dur = f" ({e['duracion_ms']:.0f} ms)" if "duracion_ms" in e else ""
        if e["tipo"] == "modelo":
            print(f"{t}  🧠 modelo · vuelta {e['vuelta']} · stop_reason={e.get('stop_reason')} · "
                  f"in={e.get('gen_ai.usage.input_tokens')} out={e.get('gen_ai.usage.output_tokens')}{dur}")
        elif e["tipo"] == "herramienta":
            marca = "❌" if e.get("is_error") else "🔧"
            print(f"{t}    {marca} {e['nombre']}({e.get('entrada')}) → {e.get('clase')}{dur}")
        elif e["tipo"] == "guardrail":
            marca = "🛡️ " if e.get("permitir") else "⛔"
            print(f"{t}  {marca} guardrail de {e['nombre']}: {'pasa' if e.get('permitir') else 'BLOQUEA'}"
                  f"{' · ' + e['motivo'] if e.get('motivo') else ''}{dur}")
        elif e["tipo"] == "freno":
            print(f"{t}  🛑 freno: {e['nombre']}")
        elif e["nombre"] == "fin":
            print(f"{t}  ✔ fin · {e.get('resultado')} · total {e.get('duracion_total_ms', 0):.0f} ms")
    costo = (tin * PRECIO_ENTRADA + tout * PRECIO_SALIDA) / 1e6
    print(f"\nTokens: {tin} de entrada + {tout} de salida · costo ≈ USD {costo:.5f} (Haiku 4.5)")


if __name__ == "__main__":
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else trazas.ultima()
    if ruta is None or not ruta.exists():
        sys.exit("No hay trazas todavía: corre antes `python agente.py \"...\"`.")
    mostrar(ruta)
