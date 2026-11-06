# SalaYa · reservas de salas de juntas

## El caso
Quién lo usa: cualquier empleado o el asistente de oficina. Qué le pide: encontrar una sala libre y reservarla.
Cómo se sabe que lo resolvió: responde con IDs reales (SAL-…, RES-…) que existen en los datos, o crea una reserva
RES-6… sin empalmarse con otra y dentro del horario de la oficina.

## Arquitectura
guardrail de entrada → orquestador (Agent SDK) → servidor MCP «salas» (buscar_salas, consultar_agenda, reservar)
/ subagente «buscador_alternativas» (solo lectura) → guardrail de salida. Hook de política: modo auditor y
reservas de más de 2 horas con motivo.
Por qué un subagente aquí: cuando el horario está ocupado, revisar varias salas y agendas son muchas llamadas;
el subagente las hace en su propio contexto y le devuelve al orquestador solo 3 opciones. Costo: una
conversación extra de solo lectura, solo cuando hay conflicto.

## Cómo correrlo
    cd ~/capstone && source .venv/bin/activate
    python agente.py "¿Qué salas hay para 6 personas con proyector?"
    python evals.py --sin-guardrails --etiqueta antes
    python evals.py --etiqueta despues && python evals.py --comparar antes despues
    python ver_traza.py > resultados/traza.txt
    python verificar_capstone.py

## Evaluación
Golden set: 10 casos (3 adversariales). Resultado antes → después: X/10 → Y/10. Qué caso falló y qué hice: …

## Guardrails
Entrada: bloquea inyecciones y enmascara contraseñas y tarjetas. Salida: reemplaza respuestas con IDs que ninguna
herramienta devolvió, promesas o tarjetas. Un falso positivo que encontré: …

## Costo
Costo por pregunta (USD): … · palanca aplicada: … · ahorro medido: …% · proyección a 1.000 preguntas/día: USD …

## Límites
Datos simulados en JSON; no cancela ni modifica reservas; no valida que el responsable exista. Con una semana
más: …