"""
Cliente de Claude para los labs de AI Engineer con Claude (AIENG01): el mismo código corre contra la API de
Anthropic o contra Amazon Bedrock, sin tocar el resto de los scripts.

- En el Cloud Workspace del curso NO hay API key de Anthropic: el acceso a Claude
  es por Amazon Bedrock, con las credenciales AWS que el workspace ya trae (perfil
  [default] de la cuenta de labs). `get_client()` devuelve `AnthropicBedrock`.
- En tu máquina, con `ANTHROPIC_API_KEY` en el entorno (o en `.env`), devuelve
  `Anthropic()` y todo funciona igual contra la API directa.

La interfaz es la misma (`messages.create`, `messages.stream`, tool use, prompt
caching, structured outputs). Diferencias que vas a notar en Bedrock:
- el id del modelo es el de un *inference profile* (`us.anthropic...`); por eso los
  scripts usan alias cortos y los traducen con `model_id()`;
- la Batches API y `models.retrieve()` no existen en Bedrock;
- la cuenta de labs solo habilita Claude Haiku 4.5 (guarda de costos del curso).
"""

import os

from anthropic import Anthropic, AnthropicBedrock
from dotenv import load_dotenv

load_dotenv()

# Alias de la API de Anthropic → inference profile de Bedrock (región us)
BEDROCK_IDS = {
    "claude-haiku-4-5": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "claude-sonnet-4-6": "us.anthropic.claude-sonnet-4-6",
    "claude-opus-4-8": "us.anthropic.claude-opus-4-8",
}


def usa_bedrock() -> bool:
    """Sin ANTHROPIC_API_KEY en el entorno, el acceso es por Bedrock."""
    return not os.environ.get("ANTHROPIC_API_KEY")


def get_client():
    if usa_bedrock():
        return AnthropicBedrock(aws_region=os.environ.get("AWS_REGION", "us-east-1"))
    return Anthropic()


def model_id(alias: str) -> str:
    """Traduce un alias (claude-haiku-4-5) al id que espera el proveedor activo."""
    return BEDROCK_IDS.get(alias, alias) if usa_bedrock() else alias


def proveedor() -> str:
    return "Amazon Bedrock" if usa_bedrock() else "API de Anthropic"


# Modelo por defecto: Haiku 4.5 en el workspace (el único habilitado en la cuenta
# de labs); Sonnet 4.6 con API key propia. Se cambia con CLAUDE_MODEL=<alias>.
DEFAULT_MODEL = os.environ.get(
    "CLAUDE_MODEL", "claude-haiku-4-5" if usa_bedrock() else "claude-sonnet-4-6"
)
