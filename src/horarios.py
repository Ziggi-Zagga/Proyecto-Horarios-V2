# =============================================================================
# horarios.py
# -----------------------------------------------------------------------------
# Responsible for:
#   1. Validating and normalising raw schedule entries.
#   2. Building the fast-lookup indices used by the algorithm.
#   3. Extracting the "equipo educativo" (educational team) for a group.
#
# This module is pure logic — no Flask, no I/O.
# =============================================================================

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from src.config import (
    CAMPOS_REQUERIDOS,
    DIAS_VALIDOS,
    HORA_RECREO,
    NUM_SESIONES,
    SESIONES_VALIDAS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public type aliases (for readability)
# ---------------------------------------------------------------------------

# Raw entry as parsed from the uploaded file.
EntradaHorario = dict[str, Any]

# ocupado[profesor_id] → set of (dia, hora) tuples where the teacher is busy.
OcupadoIndex = dict[str, set[tuple[int, int]]]

# ocupado_por_dia[profesor_id][dia] → sorted list of occupied hours that day.
OcupadoPorDia = dict[str, dict[int, list[int]]]


# ---------------------------------------------------------------------------
# 1. VALIDATION & NORMALISATION
# ---------------------------------------------------------------------------

class EntradaInvalidaError(ValueError):
    """Raised when a schedule entry fails validation."""


def _validar_entrada(entrada: EntradaHorario, idx: int) -> None:
    """
    Raise EntradaInvalidaError if *entrada* is missing required fields or
    contains out-of-range values.

    Parameters
    ----------
    entrada : dict
        A single schedule row.
    idx : int
        Row index (for error messages).
    """
    # --- Required field presence ---
    for campo in CAMPOS_REQUERIDOS:
        if campo not in entrada:
            raise EntradaInvalidaError(
                f"Fila {idx}: falta el campo obligatorio '{campo}'."
            )

    # --- Type coercion & range checks ---
    try:
        dia = int(entrada["dia"])
    except (TypeError, ValueError):
        raise EntradaInvalidaError(
            f"Fila {idx}: 'dia' debe ser un entero (recibido: {entrada['dia']!r})."
        )

    try:
        hora = int(entrada["hora"])
    except (TypeError, ValueError):
        raise EntradaInvalidaError(
            f"Fila {idx}: 'hora' debe ser un entero (recibido: {entrada['hora']!r})."
        )

    if dia not in DIAS_VALIDOS:
        raise EntradaInvalidaError(
            f"Fila {idx}: 'dia' fuera de rango — esperado 0..4, recibido {dia}."
        )

    if not (1 <= hora <= NUM_SESIONES):
        raise EntradaInvalidaError(
            f"Fila {idx}: 'hora' fuera de rango — esperado 1..{NUM_SESIONES}, recibido {hora}."
        )

    if not str(entrada["profesor_id"]).strip():
        raise EntradaInvalidaError(f"Fila {idx}: 'profesor_id' no puede estar vacío.")

    if not str(entrada["grupo"]).strip():
        raise EntradaInvalidaError(f"Fila {idx}: 'grupo' no puede estar vacío.")


def normalizar_entradas(
    entradas_raw: list[EntradaHorario],
) -> list[EntradaHorario]:
    """
    Validate, normalise, deduplicate and clean a list of raw schedule entries.

    Steps performed:
      1. Validate each entry (required fields, value ranges).
      2. Coerce ``dia`` and ``hora`` to int; strip string fields.
      3. Remove entries that fall on the recess hour.
      4. Detect and remove duplicate (profesor_id, dia, hora) combinations
         (keeping the first occurrence and logging a warning).

    Parameters
    ----------
    entradas_raw : list[dict]
        Raw entries as parsed from the uploaded file.

    Returns
    -------
    list[dict]
        Clean, deduplicated entries ready for index building.

    Raises
    ------
    EntradaInvalidaError
        If any entry fails validation.
    """
    entradas_limpias: list[EntradaHorario] = []
    vistas: set[tuple[str, int, int]] = set()   # (profesor_id, dia, hora)
    n_duplicados = 0
    n_recreo = 0

    for idx, entrada in enumerate(entradas_raw):
        _validar_entrada(entrada, idx)

        # Normalise types
        entrada = dict(entrada)  # don't mutate the original
        entrada["dia"] = int(entrada["dia"])
        entrada["hora"] = int(entrada["hora"])
        entrada["profesor_id"] = str(entrada["profesor_id"]).strip()
        entrada["grupo"] = str(entrada["grupo"]).strip()

        # Strip optional string fields if present
        for campo in ("tarea", "aula"):
            if campo in entrada and isinstance(entrada[campo], str):
                entrada[campo] = entrada[campo].strip()

        # Drop recess entries
        if HORA_RECREO is not None and entrada["hora"] == HORA_RECREO:
            n_recreo += 1
            continue

        # Deduplicate
        clave = (entrada["profesor_id"], entrada["dia"], entrada["hora"])
        if clave in vistas:
            n_duplicados += 1
            logger.warning(
                "Entrada duplicada ignorada: profesor=%s día=%d hora=%d",
                *clave,
            )
            continue

        vistas.add(clave)
        entradas_limpias.append(entrada)

    if n_recreo:
        logger.info("Se eliminaron %d entradas de recreo.", n_recreo)
    if n_duplicados:
        logger.warning("Se eliminaron %d entradas duplicadas.", n_duplicados)

    logger.info(
        "Normalización completada: %d entradas válidas de %d originales.",
        len(entradas_limpias),
        len(entradas_raw),
    )

    return entradas_limpias


# ---------------------------------------------------------------------------
# 2. INDEX BUILDING
# ---------------------------------------------------------------------------

def build_indices(
    entradas: list[EntradaHorario],
) -> tuple[OcupadoIndex, OcupadoPorDia]:
    """
    Build the two fast-lookup structures used by the backtracking algorithm.

    Parameters
    ----------
    entradas : list[dict]
        Normalised schedule entries (output of :func:`normalizar_entradas`).

    Returns
    -------
    ocupado : dict[str, set[tuple[int,int]]]
        ``ocupado[profesor_id]`` → set of ``(dia, hora)`` pairs where the
        teacher is occupied.

    ocupado_por_dia : dict[str, dict[int, list[int]]]
        ``ocupado_por_dia[profesor_id][dia]`` → **sorted** list of occupied
        hours that day.  Used for O(log n) binary-search penalty lookups.
    """
    # Use defaultdict internally for convenient building, then convert.
    _ocupado: dict[str, set[tuple[int, int]]] = defaultdict(set)
    _por_dia: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))

    for entrada in entradas:
        pid = entrada["profesor_id"]
        dia = entrada["dia"]
        hora = entrada["hora"]

        # Skip sessions that are not in the valid session list
        # (e.g. recess already removed, but belt-and-suspenders check)
        if hora not in SESIONES_VALIDAS:
            continue

        _ocupado[pid].add((dia, hora))
        _por_dia[pid][dia].append(hora)

    # Sort each day's list so binary search works correctly.
    ocupado_por_dia: OcupadoPorDia = {}
    for pid, dias_dict in _por_dia.items():
        ocupado_por_dia[pid] = {
            dia: sorted(horas) for dia, horas in dias_dict.items()
        }

    ocupado: OcupadoIndex = dict(_ocupado)

    logger.info(
        "Índices construidos: %d profesores en el sistema.",
        len(ocupado),
    )

    return ocupado, ocupado_por_dia


# ---------------------------------------------------------------------------
# 3. EDUCATIONAL TEAM EXTRACTION
# ---------------------------------------------------------------------------

def get_equipo_educativo(
    entradas: list[EntradaHorario],
    grupo_objetivo: str,
) -> list[str]:
    """
    Return the **sorted** list of teacher IDs that teach the target group.

    A teacher belongs to the educational team if they have at least one
    schedule entry where ``grupo == grupo_objetivo``.

    Parameters
    ----------
    entradas : list[dict]
        Normalised schedule entries.
    grupo_objetivo : str
        The student group to look up (e.g. ``"2ESO-A"``).

    Returns
    -------
    list[str]
        Sorted list of unique ``profesor_id`` values.  Empty if the group
        is not found.
    """
    grupo_objetivo = grupo_objetivo.strip()
    equipo: set[str] = {
        e["profesor_id"]
        for e in entradas
        if e["grupo"] == grupo_objetivo
    }

    sorted_equipo = sorted(equipo)

    logger.info(
        "Equipo educativo de '%s': %d profesores → %s",
        grupo_objetivo,
        len(sorted_equipo),
        sorted_equipo,
    )

    return sorted_equipo


def get_grupos_disponibles(entradas: list[EntradaHorario]) -> list[str]:
    """
    Return a sorted list of all unique group names present in the schedule.

    Parameters
    ----------
    entradas : list[dict]
        Normalised schedule entries.

    Returns
    -------
    list[str]
        Sorted unique group names.
    """
    return sorted({e["grupo"] for e in entradas})
