"""
L8 (♻ TL03 Lab 04) · Utilidades de costeo y registro de usage.

Importado por los demás scripts del lab y por servicio.py. El log va a usage_log.jsonl (o a la ruta de la
variable USAGE_LOG, que usa verificar.py para no ensuciar el tuyo).
"""

import json
import os
import time
from functools import lru_cache
from pathlib import Path

# Precios USD por millón de tokens (verifica contra la documentación vigente)
PRICES = {
    "claude-opus-4-8":   {"input": 5.00, "output": 25.00, "cache_write": 6.25, "cache_read": 0.50},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    "claude-haiku-4-5":  {"input": 1.00, "output": 5.00,  "cache_write": 1.25, "cache_read": 0.10},
}

LOG_PATH = Path(os.environ.get("USAGE_LOG", Path(__file__).parent / "usage_log.jsonl"))


@lru_cache(maxsize=None)
def _modelo_del_perfil(arn: str) -> str | None:
    """Modelo detrás de un application inference profile de Bedrock (el ARN que trae CLAUDE_MODEL en el
    Cloud Workspace: un perfil por cohorte para atribuir el costo). None si no se puede consultar."""
    try:
        import botocore.session
        region = arn.split(":")[3] or os.environ.get("AWS_REGION", "us-east-1")
        bedrock = botocore.session.get_session().create_client("bedrock", region_name=region)
        modelos = bedrock.get_inference_profile(inferenceProfileIdentifier=arn).get("models") or []
        return modelos[0]["modelArn"] if modelos else None
    except Exception:
        return None


@lru_cache(maxsize=None)
def precio_alias(model: str) -> str:
    """Alias de PRICES para cualquier forma del id: alias corto (claude-haiku-4-5), id de Bedrock
    (us.anthropic.claude-haiku-4-5-20251001-v1:0) o ARN de un application inference profile."""
    if model in PRICES:
        return model
    candidato = model
    if ":application-inference-profile/" in model:
        candidato = _modelo_del_perfil(model) or os.environ.get("CLAUDE_MODEL_BASE", "")
    for alias in PRICES:
        if alias in candidato:
            return alias
    # El rol del Cloud Workspace no puede leer el perfil (bedrock:GetInferenceProfile) y los perfiles de las
    # cohortes de este curso son de Haiku 4.5: se costea como Haiku. Con otro modelo, fija CLAUDE_MODEL_BASE.
    if ":application-inference-profile/" in model:
        return "claude-haiku-4-5"
    raise KeyError(f"Sin precio para el modelo {model!r}: agrégalo a PRICES en costing.py")


def cost_usd(usage, model: str, batch: bool = False) -> float:
    """Costo real de un request: las 4 líneas de usage. Batch = 50% off."""
    p = PRICES[precio_alias(model)]
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    total = (
        usage.input_tokens * p["input"]
        + cache_write * p["cache_write"]
        + cache_read * p["cache_read"]
        + usage.output_tokens * p["output"]
    ) / 1_000_000
    return total * 0.5 if batch else total


def log_usage(feature: str, model: str, usage, latency_ms: float = 0.0,
              batch: bool = False, **extra) -> dict:
    """Registra un request en usage_log.jsonl — la fuente del dashboard."""
    entry = {
        "ts": time.time(),
        "feature": feature,
        "model": precio_alias(model),
        "input_tokens": usage.input_tokens,
        "cache_write": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "output_tokens": usage.output_tokens,
        "cost_usd": round(cost_usd(usage, model, batch=batch), 8),
        "latency_ms": round(latency_ms, 1),
        "batch": batch,
        **extra,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_log() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    return [json.loads(line) for line in LOG_PATH.read_text(encoding="utf-8").splitlines() if line]
