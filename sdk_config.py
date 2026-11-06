"""
Configuración del Claude Agent SDK para los labs de AIENG01.

El SDK no llama a la Messages API directamente: arranca un Claude Code (viene empaquetado con el SDK) y le
habla por un canal propio. Por eso el proveedor se elige con variables de entorno, no con un cliente:

- En el Cloud Workspace NO hay API key. Hay dos rutas, y el workspace ya trae configurada la suya:
  * Gateway del curso (`BOOTCAMP_CLAUDE_ROUTE=gateway`): Claude Code habla con el gateway de la cohorte
    (`ANTHROPIC_BASE_URL` + token), que solo acepta sus alias de modelo (`bedrock-claude-haiku`,
    `bedrock-claude-sonnet`). Un id de Bedrock (`us.anthropic...`) ahí da `403 key not allowed to access model`.
  * Amazon Bedrock directo, con las credenciales AWS del workspace (`CLAUDE_CODE_USE_BEDROCK=1`).
- En tu máquina, con `ANTHROPIC_API_KEY`, va contra la API directa.

El modelo es Claude Haiku 4.5 en las tres rutas. Se cambia con CLAUDE_MODEL_SDK.

Al correr con el gateway, Claude Code imprime `[claude-code:unrecognized_model] {"model":"bedrock-claude-haiku"...}`:
es un aviso de que no conoce ese alias (lo usa para titular la sesión), no un error. La respuesta llega igual.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()

# El workspace declara su ruta en el entorno de la terminal y en la política de Claude Code; se leen los dos
# porque una terminal abierta antes de configurar el workspace puede no tener las variables.
_POLITICA = "/etc/claude-code/managed-settings.json"


def _entorno_politica() -> dict:
    try:
        with open(_POLITICA) as f:
            return json.load(f).get("env", {}) or {}
    except (OSError, ValueError):
        return {}


_POL = _entorno_politica()
USA_GATEWAY = (os.environ.get("BOOTCAMP_CLAUDE_ROUTE") or _POL.get("BOOTCAMP_CLAUDE_ROUTE")) == "gateway"
USA_BEDROCK = not USA_GATEWAY and not os.environ.get("ANTHROPIC_API_KEY")
if USA_BEDROCK:
    os.environ.setdefault("CLAUDE_CODE_USE_BEDROCK", "1")
    os.environ.setdefault("AWS_REGION", "us-east-1")

if USA_GATEWAY:
    _DEFECTO = (
        os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL")
        or _POL.get("ANTHROPIC_DEFAULT_HAIKU_MODEL")
        or "bedrock-claude-haiku"
    )
elif USA_BEDROCK:
    _DEFECTO = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
else:
    _DEFECTO = "claude-haiku-4-5"

MODELO = os.environ.get("CLAUDE_MODEL_SDK") or _DEFECTO


def proveedor() -> str:
    if USA_GATEWAY:
        return "Gateway del curso (Bedrock)"
    return "Amazon Bedrock" if USA_BEDROCK else "API de Anthropic"
