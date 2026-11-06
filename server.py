"""
Capstone · Servidor MCP propio de reservas de salas de juntas (♻ plantilla del L3).

Expone 3 herramientas sobre datos simulados (datos/*.json). FastMCP arma el schema de entrada con los type
hints (Literal → enum) y usa el docstring como la descripción que lee el modelo: escríbelo PARA el modelo
(cuándo usarla, qué devuelve, qué hacer si falla).


"""

import json
import os
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

mcp = FastMCP("casos-pagosya", log_level="WARNING")  # sin el log de cada request en stderr

# CASOS_DB permite apuntar a otra copia (verificar.py trabaja sobre una copia temporal y no toca la tuya)
DB_PATH = Path(os.environ.get("CASOS_DB", Path(__file__).parent / "casos.json"))

Estado = Literal["abierto", "en_proceso", "escalado", "cerrado"]
Prioridad = Literal["alta", "media", "baja"]


def _load() -> dict:
    return json.loads(DB_PATH.read_text(encoding="utf-8"))


def _save(db: dict) -> None:
    DB_PATH.write_text(json.dumps(db, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _caso(db: dict, case_id: str) -> dict:
    if case_id not in db:
        raise ToolError(f"No existe el caso {case_id}. Usa search_cases para encontrar el ID correcto (formato CASE-NNNN).")
    return db[case_id]


# ── Herramientas de LECTURA ───────────────────────────────────────────────────────────────────

@mcp.tool()
def buscar_salas(capacidad: int, equipo: Literal["cualquiera", "proyector", "videollamada"] = "cualquiera") -> list[dict]:
    """Lista las salas con al menos `capacidad` lugares y, si se pide, con proyector o videollamada.
    Úsala cuando el usuario no dice qué sala quiere. Devuelve id (SAL-…), nombre, piso, capacidad y equipo.
    Si no hay ninguna, devuelve una lista vacía: díselo al usuario y ofrece bajar la capacidad o quitar el equipo."""
    if capacidad < 1:
        raise ValueError("La capacidad debe ser al menos 1 persona. Pregunta cuántas personas asistirán.")
    return [s for s in _cargar("salas.json")
            if s["capacidad"] >= capacidad and (equipo == "cualquiera" or equipo in s["equipo"])]


@mcp.tool()
def consultar_agenda(sala_id: str, fecha: str) -> dict:
    """Devuelve las reservas de una sala (SAL-…) en una fecha (AAAA-MM-DD), ordenadas por hora, y el horario de
    la oficina. Úsala ANTES de decir si una sala está libre. Si la fecha no tiene el formato AAAA-MM-DD, el
    error lo dice: pide la fecha exacta, no la adivines."""
    sala = _sala(sala_id)
    try:
        datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"La fecha «{fecha}» no tiene el formato AAAA-MM-DD. Pide al usuario la fecha exacta.")
    ocupadas = sorted((r for r in _reservas() if r["sala_id"] == sala["id"] and r["fecha"] == fecha),
                      key=lambda r: r["inicio"])
    return {"sala_id": sala["id"], "fecha": fecha, "horario": f"{APERTURA}-{CIERRE}",
            "reservas": [{k: r[k] for k in ("id", "inicio", "fin", "responsable")} for r in ocupadas]}


@mcp.tool()
def reservar(sala_id: str, fecha: str, hora_inicio: str, duracion_min: int, responsable: str, motivo: str) -> dict:
    """Reserva una sala. Úsala solo cuando tengas sala (SAL-…), fecha (AAAA-MM-DD), hora de inicio (HH:MM),
    duración en minutos, el login del responsable y el motivo; si falta alguno, PÍDELO. Rechaza horarios ocupados
    o fuera de 08:00-19:00 con un error que dice qué hacer. Es idempotente: la misma sala, fecha, hora y
    responsable devuelven la reserva ya creada."""
    sala = _sala(sala_id)
    try:
        inicio = datetime.strptime(f"{fecha} {hora_inicio}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError("Fecha u hora inválidas: usa AAAA-MM-DD y HH:MM (24 h). Pide el dato exacto al usuario.")
    if not 15 <= duracion_min <= MAX_MIN:
        raise ValueError(f"La duración debe estar entre 15 y {MAX_MIN} minutos. Pregunta cuánto durará la junta.")
    fin = inicio + timedelta(minutes=duracion_min)
    h_ini, h_fin = inicio.strftime("%H:%M"), fin.strftime("%H:%M")
    if h_ini < APERTURA or h_fin > CIERRE or fin.date() != inicio.date():
        raise ValueError(f"Fuera del horario de la oficina ({APERTURA}-{CIERRE}). Propón otro horario.")
    clave = hashlib.sha256(f"{sala['id']}|{fecha}|{h_ini}|{responsable.strip().lower()}".encode()).hexdigest()[:12]
    nuevas = _nuevas()
    for r in nuevas:
        if r["clave"] == clave:                       # idempotencia (L2): el reintento no duplica
            return {**r, "nota": "ya existía: no se duplicó"}
    for r in _reservas():
        if r["sala_id"] == sala["id"] and r["fecha"] == fecha and r["inicio"] < h_fin and h_ini < r["fin"]:
            raise ValueError(f"La {sala['id']} está ocupada de {r['inicio']} a {r['fin']} ({r['id']}). "
                             "No insistas con ese horario: consulta la agenda y propón otra hora u otra sala.")
    reserva = {"id": f"RES-{6001 + len(nuevas)}", "sala_id": sala["id"], "fecha": fecha, "inicio": h_ini, "fin": h_fin,
               "responsable": responsable.strip().lower(), "motivo": motivo.strip(), "clave": clave}
    NUEVAS.write_text(json.dumps(nuevas + [reserva], ensure_ascii=False, indent=2), encoding="utf-8")
    return reserva


if __name__ == "__main__":
    mcp.run()  # transporte stdio por defecto
