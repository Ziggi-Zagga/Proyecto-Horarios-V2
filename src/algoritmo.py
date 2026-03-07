# =============================================================================
# algoritmo.py
# -----------------------------------------------------------------------------
# Core scheduling algorithm.
#
# GOAL
# ----
# Given a student group, find the (dia, hora) slot where ALL teachers of that
# group are simultaneously free, optimising lexicographically:
#
#   1. Minimise total penalty  (coste_total)
#   2. Minimise worst individual penalty  (peor_penalizacion)
#   3. Choose the earliest slot chronologically  (implicit via slot order)
#
# PENALTY MODEL
# -------------
# For teacher p at candidate slot (dia, hora):
#
#   • If p has occupied sessions on *dia*:
#       penalty = min(|occupied_hour − hora|)  for all occupied hours that day
#   • If p has NO sessions on *dia*:
#       penalty = PENALIZACION_DIA_LIBRE  (default 7)
#
# Binary search (bisect) is used to find the nearest occupied hour in O(log n).
#
# ALGORITHM: BACKTRACKING + BRANCH & BOUND
# -----------------------------------------
# Candidates are evaluated in chronological order (Monday … Friday, session
# 1 … 7 modulo recess).  For each candidate slot:
#
#   1. Check the HARD CONSTRAINT: every teacher must be free that slot.
#   2. Iterate through the team, accumulating partial sum and partial max.
#   3. PRUNE early if the partial totals already equal or exceed the current
#      best — there is no way this slot can improve the solution.
#   4. If the slot survives, compare it to the current best and update.
#
# =============================================================================

from __future__ import annotations

import bisect
import logging
from typing import Any

from src.config import (
    PENALIZACION_DIA_LIBRE,
    PERMITIR_HORAS_SIN_CLASE,
    SLOTS_CALENDARIO,
)
from src.horarios import (
    OcupadoIndex,
    OcupadoPorDia,
    build_indices,
    get_equipo_educativo,
    normalizar_entradas,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Type alias for the result structure
# ---------------------------------------------------------------------------

ResultadoSlot = dict[str, Any]


# ---------------------------------------------------------------------------
# 1. PENALTY CALCULATION
# ---------------------------------------------------------------------------

def calcular_penalizacion(
    profesor_id: str,
    dia: int,
    hora: int,
    ocupado_por_dia: OcupadoPorDia,
) -> int:
    """
    Calculate the penalty for placing teacher *profesor_id* at slot (dia, hora).

    Algorithm
    ---------
    1. Look up the sorted list of occupied hours for this teacher on *dia*.
    2. If the list is empty → return PENALIZACION_DIA_LIBRE.
    3. Otherwise use binary search (bisect_left) to find the insertion point
       of *hora* in the sorted list.  The nearest element is either at the
       insertion point or one position to the left — check both and take the
       minimum distance.

    Parameters
    ----------
    profesor_id : str
    dia         : int  (0 = Monday … 4 = Friday)
    hora        : int  (1-based session number)
    ocupado_por_dia : OcupadoPorDia

    Returns
    -------
    int
        Non-negative penalty value.
    """
    # Retrieve hours occupied by this teacher on the given day.
    horas_ocupadas: list[int] = (
        ocupado_por_dia
        .get(profesor_id, {})
        .get(dia, [])
    )

    # No sessions that day → maximum penalty (teacher is completely free)
    if not horas_ocupadas:
        return PENALIZACION_DIA_LIBRE

    # Binary search: find where *hora* would be inserted to keep sorted order.
    pos = bisect.bisect_left(horas_ocupadas, hora)

    # The nearest neighbour is either at pos or pos-1.
    # We collect both candidates (where they exist) and take the minimum distance.
    distancias: list[int] = []

    if pos < len(horas_ocupadas):
        distancias.append(abs(horas_ocupadas[pos] - hora))

    if pos > 0:
        distancias.append(abs(horas_ocupadas[pos - 1] - hora))

    return min(distancias)


# ---------------------------------------------------------------------------
# 2. HARD CONSTRAINT CHECK
# ---------------------------------------------------------------------------

def slot_es_libre_para_todos(
    equipo: list[str],
    dia: int,
    hora: int,
    ocupado: OcupadoIndex,
) -> bool:
    """
    Return True iff every teacher in *equipo* is free at (dia, hora).

    A teacher is free at a slot if (dia, hora) is NOT in their occupied set.

    Parameters
    ----------
    equipo  : list[str]  — teacher IDs in the educational team
    dia     : int
    hora    : int
    ocupado : OcupadoIndex
    """
    for pid in equipo:
        if (dia, hora) in ocupado.get(pid, set()):
            return False
    return True


# ---------------------------------------------------------------------------
# 3. DETAIL BUILDER — per-teacher information for the output
# ---------------------------------------------------------------------------

def _construir_detalle(
    equipo: list[str],
    dia: int,
    hora: int,
    ocupado_por_dia: OcupadoPorDia,
) -> list[dict[str, Any]]:
    """
    Build the per-teacher detail list for the final result structure.

    For each teacher, records:
      • penalizacion
      • sesion_ocupada_mas_cercana (the occupied hour closest to *hora*,
        or None if the teacher has no sessions that day)
      • tiene_sesiones_ese_dia

    Parameters
    ----------
    equipo          : list[str]
    dia             : int
    hora            : int
    ocupado_por_dia : OcupadoPorDia

    Returns
    -------
    list[dict]
    """
    detalle = []

    for pid in equipo:
        horas_ocupadas = ocupado_por_dia.get(pid, {}).get(dia, [])
        tiene_sesiones = bool(horas_ocupadas)
        penalizacion = calcular_penalizacion(pid, dia, hora, ocupado_por_dia)

        # Find the actual nearest occupied hour (for display purposes)
        sesion_cercana: int | None = None
        if horas_ocupadas:
            pos = bisect.bisect_left(horas_ocupadas, hora)
            candidatos: list[int] = []
            if pos < len(horas_ocupadas):
                candidatos.append(horas_ocupadas[pos])
            if pos > 0:
                candidatos.append(horas_ocupadas[pos - 1])
            sesion_cercana = min(candidatos, key=lambda h: abs(h - hora))

        detalle.append({
            "profesor_id": pid,
            "penalizacion": penalizacion,
            "sesion_ocupada_mas_cercana": sesion_cercana,
            "tiene_sesiones_ese_dia": tiene_sesiones,
        })

    return detalle


# ---------------------------------------------------------------------------
# 4. BACKTRACKING + BRANCH & BOUND
# ---------------------------------------------------------------------------

def find_best_meeting_slot(
    entradas_raw: list[dict[str, Any]],
    grupo_objetivo: str,
) -> ResultadoSlot:
    """
    Find the optimal evaluation meeting slot for *grupo_objetivo*.

    This is the main entry point called by the Flask application.

    Steps
    -----
    1. Normalise and validate the raw input.
    2. Build fast-lookup indices.
    3. Extract the educational team for the target group.
    4. Run the backtracking + branch & bound optimisation.
    5. Return a structured result dictionary.

    Parameters
    ----------
    entradas_raw    : list[dict]  — raw schedule entries (from upload)
    grupo_objetivo  : str         — target student group, e.g. ``"2ESO-A"``

    Returns
    -------
    dict
        Either a full result with ``"slot_optimo"`` or ``{"sin_solucion": True}``.
    """

    # ------------------------------------------------------------------
    # Step 1 — Normalise
    # ------------------------------------------------------------------
    entradas = normalizar_entradas(entradas_raw)

    # ------------------------------------------------------------------
    # Step 2 — Build indices
    # ------------------------------------------------------------------
    ocupado, ocupado_por_dia = build_indices(entradas)

    # ------------------------------------------------------------------
    # Step 3 — Educational team
    # ------------------------------------------------------------------
    equipo = get_equipo_educativo(entradas, grupo_objetivo)

    if not equipo:
        logger.warning("No se encontró equipo educativo para el grupo '%s'.", grupo_objetivo)
        return {"sin_solucion": True, "motivo": f"No hay profesores para el grupo '{grupo_objetivo}'."}

    logger.info(
        "Iniciando backtracking para grupo '%s' con %d profesores y %d slots candidatos.",
        grupo_objetivo,
        len(equipo),
        len(SLOTS_CALENDARIO),
    )

    # ------------------------------------------------------------------
    # Step 4 — Backtracking + Branch & Bound
    # ------------------------------------------------------------------

    # Sentinel "infinity" values for the initial best.
    # We use a large integer rather than math.inf to keep everything as int.
    _INF = 10 ** 9

    best_coste_total:     int = _INF   # best total penalty found so far
    best_peor_pen:        int = _INF   # best worst-individual penalty so far
    best_slot:  tuple[int, int] | None = None

    # Counters for logging / diagnostics
    slots_evaluados   = 0
    slots_podados     = 0
    slots_validos     = 0

    # Iterate through every candidate slot in chronological order.
    # The order (Monday … Friday, session 1 … N) acts as the implicit
    # tie-breaker (earliest slot wins when all other criteria are equal).
    for (dia, hora) in SLOTS_CALENDARIO:

        # ----------------------------------------------------------------
        # HARD CONSTRAINT: every teacher must be free at this slot.
        # ----------------------------------------------------------------
        if not slot_es_libre_para_todos(equipo, dia, hora, ocupado):
            slots_evaluados += 1
            continue   # This slot cannot be used — skip immediately.

        slots_validos += 1

        # ----------------------------------------------------------------
        # BRANCH & BOUND — accumulate penalties teacher by teacher.
        # ----------------------------------------------------------------
        # We evaluate teachers one at a time, maintaining running totals.
        # As soon as the running totals can no longer beat the current best,
        # we PRUNE (break early) without evaluating the remaining teachers.

        suma_parcial = 0   # running sum of penalties so far
        max_parcial  = 0   # running maximum penalty so far
        pruned       = False

        for pid in equipo:

            # Skip slots where teacher has no class if policy forbids it
            horas_dia = ocupado_por_dia.get(pid, {}).get(dia, [])
            if not PERMITIR_HORAS_SIN_CLASE and not horas_dia:
                # Treat as infeasible for this teacher
                pruned = True
                break

            # Compute this teacher's penalty for the candidate slot.
            pen = calcular_penalizacion(pid, dia, hora, ocupado_por_dia)

            suma_parcial += pen
            if pen > max_parcial:
                max_parcial = pen

            # --------------------------------------------------------
            # PRUNING CONDITION
            # --------------------------------------------------------
            # We can prune if the partial sum already exceeds the best
            # total, OR if it equals the best total but the partial max
            # already meets or exceeds the best worst penalty.
            #
            # Why "meets or exceeds" (>=) for max_parcial?
            # Because even if suma_parcial == best_coste_total, we can
            # only improve the second criterion if max_parcial is
            # *strictly less* than best_peor_pen.  If it is already
            # equal, the remaining teachers can only keep it equal or
            # make it worse → prune.
            # --------------------------------------------------------
            if suma_parcial > best_coste_total:
                pruned = True
                slots_podados += 1
                break

            if (suma_parcial == best_coste_total and
                    max_parcial >= best_peor_pen):
                pruned = True
                slots_podados += 1
                break

        # ----------------------------------------------------------------
        # UPDATE BEST — only if we processed all teachers without pruning.
        # ----------------------------------------------------------------
        if not pruned:
            # Lexicographic comparison:
            #   (suma_parcial, max_parcial)  vs  (best_coste_total, best_peor_pen)
            # Slot order already guarantees the chronological tie-breaker
            # because we iterate in chronological order and only accept
            # strictly better solutions (not equal ones after pruning).

            if (
                best_slot is None
                or suma_parcial < best_coste_total
                or (suma_parcial == best_coste_total and max_parcial < best_peor_pen)
            ):
                best_coste_total = suma_parcial
                best_peor_pen    = max_parcial
                best_slot        = (dia, hora)

                logger.debug(
                    "  ✓ Nuevo mejor slot: día=%d hora=%d → coste=%d máx_pen=%d",
                    dia, hora, best_coste_total, best_peor_pen,
                )

        slots_evaluados += 1

    # ------------------------------------------------------------------
    # Step 5 — Build and return result
    # ------------------------------------------------------------------
    logger.info(
        "Backtracking completado: evaluados=%d válidos=%d podados=%d",
        slots_evaluados,
        slots_validos,
        slots_podados,
    )

    if best_slot is None:
        logger.warning("No se encontró ningún slot válido para el grupo '%s'.", grupo_objetivo)
        return {"sin_solucion": True, "motivo": "No existe ningún slot donde todos los profesores estén libres."}

    # Build per-teacher detail for the winning slot.
    detalle = _construir_detalle(equipo, best_slot[0], best_slot[1], ocupado_por_dia)

    return {
        "slot_optimo":        best_slot,
        "coste_total":        best_coste_total,
        "peor_penalizacion":  best_peor_pen,
        "equipo_educativo":   equipo,
        "grupo":              grupo_objetivo,
        "detalle_por_profesor": detalle,
    }
