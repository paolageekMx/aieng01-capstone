"""
L7 · Paso 2: trazas estructuradas del agente.

Una traza es la historia de UNA pregunta: cada guardrail que se evaluó, cada llamada al modelo y cada
herramienta, con su duración, sus tokens y cómo terminó. Se escribe como JSONL (un evento por línea)
en trazas/<traza_id>.jsonl, para poder leerla después con ver_traza.py o cargarla en cualquier
herramienta de observabilidad.

Los nombres de los atributos siguen la idea de las convenciones «gen_ai» de OpenTelemetry
(gen_ai.request.model, gen_ai.usage.input_tokens, ...). Aquí no usamos OpenTelemetry para no sumar
dependencias, pero un span de este archivo se traduce uno a uno a un span de OTel.
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

DIR_TRAZAS = Path(__file__).parent / "trazas"


class Traza:
    def __init__(self, pregunta: str, guardar: bool = True):
        self.id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.eventos: list[dict] = []
        self.guardar = guardar
        self._inicio = time.monotonic()
        self.evento("traza", "inicio", pregunta=pregunta)

    def evento(self, tipo: str, nombre: str, **atributos) -> dict:
        e = {"traza_id": self.id, "t_ms": round((time.monotonic() - self._inicio) * 1000, 1),
             "tipo": tipo, "nombre": nombre, **atributos}
        self.eventos.append(e)
        return e

    @contextmanager
    def span(self, tipo: str, nombre: str, **atributos):
        """Mide la duración de un bloque. Dentro, completa atributos con `s["clave"] = valor`."""
        s = {"traza_id": self.id, "t_ms": round((time.monotonic() - self._inicio) * 1000, 1),
             "tipo": tipo, "nombre": nombre, **atributos}
        inicio = time.monotonic()
        try:
            yield s
        except Exception as exc:
            s["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            s["duracion_ms"] = round((time.monotonic() - inicio) * 1000, 1)
            self.eventos.append(s)

    def cerrar(self, **atributos) -> Path | None:
        self.evento("traza", "fin", duracion_total_ms=round((time.monotonic() - self._inicio) * 1000, 1), **atributos)
        if not self.guardar:
            return None
        DIR_TRAZAS.mkdir(exist_ok=True)
        ruta = DIR_TRAZAS / f"{self.id}.jsonl"
        with ruta.open("w", encoding="utf-8") as f:
            for e in sorted(self.eventos, key=lambda e: e["t_ms"]):
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return ruta


def leer(ruta: Path) -> list[dict]:
    return [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]


def ultima() -> Path | None:
    archivos = sorted(DIR_TRAZAS.glob("*.jsonl")) if DIR_TRAZAS.exists() else []
    return archivos[-1] if archivos else None
