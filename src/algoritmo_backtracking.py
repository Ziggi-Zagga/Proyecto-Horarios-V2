"""
algoritmo_backtracking.py
─────────────────────────────────────────────────────────────────────────────
Implementa la búsqueda del mejor slot de evaluación usando Backtracking con
poda Branch & Bound, según las especificaciones del proyecto.

Interfaz pública:
    build_indices(horario, config)  →  indices
    get_team_for_group(horario, grupo_objetivo)  →  set[profesor_id]
    find_best_meeting_slot(indices, equipo_educativo, config)  →  resultado
"""

from bisect import bisect_left
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURACIÓN POR DEFECTO
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_DEFAULT = {
    # Sesiones lectivas del día (1-7). El recreo se marca aparte.
    "sesiones_totales": 7,

    # Número de sesión que es el recreo (se excluye como candidata)
    # En un horario con 7 sesiones lectivas y recreo tras la 4ª,
    # el recreo sería la posición 4 del bloque de mañana.
    # Podemos simplemente no añadirla a sesiones_validas si no se permite.
    "hora_recreo": 4,

    # Si False, la sesión 7 nunca es candidata
    "permitir_septima": False,

    # Si True, el recreo puede ser slot candidato
    "permitir_recreo": False,

    # Días válidos (0=Lunes … 4=Viernes)
    "dias_validos": list(range(5)),

    # Penalización máxima cuando el profesor no tiene sesiones ese día
    "penalizacion_sin_sesiones": 7,

    # Horas no lectivas que cuentan como LIBRES (no bloquean el slot)
    # Ej: ["GUARDIA", "REUNION", "1104"]
    "horas_no_lectivas_libres": [],
}

DIAS_NOMBRE = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes"}


# ─────────────────────────────────────────────────────────────────────────────
#  PASO 1 — CONSTRUCCIÓN DE ÍNDICES
# ─────────────────────────────────────────────────────────────────────────────

def build_indices(horario: list[dict], config: dict) -> dict:
    """
    A partir de la lista plana de sesiones (salida de get_horario_global),
    construye las estructuras internas que necesita el algoritmo.

    Parámetros
    ----------
    horario : list[dict]
        Cada dict tiene: profesor_id, dia (0-4), hora (int 1-7), grupo, tarea, aula
    config  : dict
        Opciones (se fusiona con CONFIG_DEFAULT)

    Devuelve
    --------
    dict con:
        cfg              – configuración efectiva
        sesiones_validas – list[int] sesiones que pueden ser candidatas
        slots_calendario – list[(dia, hora)] todos los slots candidatos
        ocupado          – {profesor_id: set((dia, hora))}
        ocupado_por_dia  – {profesor_id: {dia: list[int] ordenada}}
    """
    cfg = {**CONFIG_DEFAULT, **config}

    # ── Sesiones válidas ────────────────────────────────────────────────────
    sesiones = list(range(1, cfg["sesiones_totales"] + 1))

    if not cfg["permitir_recreo"]:
        sesiones = [s for s in sesiones if s != cfg["hora_recreo"]]

    if not cfg["permitir_septima"]:
        sesiones = [s for s in sesiones if s != cfg["sesiones_totales"]]

    cfg["sesiones_validas"] = sesiones

    # ── Slots del calendario ────────────────────────────────────────────────
    slots_calendario = [
        (dia, hora)
        for dia in cfg["dias_validos"]
        for hora in sesiones
    ]

    # ── Índices de ocupación ────────────────────────────────────────────────
    ocupado: dict[str, set] = {}
    ocupado_por_dia: dict[str, dict[int, list]] = {}

    no_lectivas_libres = {t.upper() for t in cfg.get("horas_no_lectivas_libres", [])}

    for sesion in horario:
        pid  = sesion["profesor_id"]
        dia  = sesion["dia"]
        hora = sesion["hora"]
        tarea = sesion.get("tarea", "").upper()

        # Si la tarea es una hora no lectiva marcada como libre → no bloquea
        if any(nl in tarea for nl in no_lectivas_libres):
            continue

        # Normalizar día
        if isinstance(dia, str):
            dia_map = {"lunes":0,"martes":1,"miércoles":2,"miercoles":2,"jueves":3,"viernes":4}
            dia = dia_map.get(dia.lower(), dia)

        # Filtrar recreo
        if hora == cfg["hora_recreo"] and not cfg["permitir_recreo"]:
            continue

        ocupado.setdefault(pid, set()).add((dia, hora))
        ocupado_por_dia.setdefault(pid, {}).setdefault(dia, [])
        if hora not in ocupado_por_dia[pid][dia]:
            ocupado_por_dia[pid][dia].append(hora)

    # Ordenar listas de horas ocupadas por día (para búsqueda binaria)
    for pid in ocupado_por_dia:
        for dia in ocupado_por_dia[pid]:
            ocupado_por_dia[pid][dia].sort()

    return {
        "cfg": cfg,
        "sesiones_validas": sesiones,
        "slots_calendario": slots_calendario,
        "ocupado": ocupado,
        "ocupado_por_dia": ocupado_por_dia,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  PASO 2 — EQUIPO EDUCATIVO
# ─────────────────────────────────────────────────────────────────────────────

def get_team_for_group(horario: list[dict], grupo_objetivo: str) -> set:
    """
    Devuelve el conjunto de profesor_id que dan clase al grupo_objetivo.
    Compara con el primer token del grupo (antes del primer '-').
    """
    objetivo = grupo_objetivo.strip().upper()
    return {
        s["profesor_id"]
        for s in horario
        if s.get("grupo", "").strip().upper() == objetivo
    }


# ─────────────────────────────────────────────────────────────────────────────
#  PASO 3 — CÁLCULO DE PENALIZACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def penalizacion(pid: str, dia: int, hora: int, indices: dict) -> float:
    """
    Calcula la penalización de un profesor para un slot (dia, hora).

    Reglas (según especificación):
      - Si no tiene sesiones ese día → penalización = 7 (máxima).
      - Si tiene sesiones → distancia mínima en saltos de sesión lectiva
        al evento ocupado más cercano en ese mismo día.
        Búsqueda binaria O(log K).
    """
    horas_dia = indices["ocupado_por_dia"].get(pid, {}).get(dia, [])

    if not horas_dia:
        return indices["cfg"]["penalizacion_sin_sesiones"]

    # Búsqueda binaria del vecino más cercano
    pos = bisect_left(horas_dia, hora)
    mejor = float("inf")

    if pos < len(horas_dia):
        mejor = min(mejor, abs(horas_dia[pos] - hora))
    if pos > 0:
        mejor = min(mejor, abs(horas_dia[pos - 1] - hora))

    return mejor


# ─────────────────────────────────────────────────────────────────────────────
#  PASO 4 — BACKTRACKING + PODA
# ─────────────────────────────────────────────────────────────────────────────

def find_best_meeting_slot(
    indices: dict,
    equipo_educativo: set,
    config: dict,
    grupo_objetivo: Optional[str] = None,
) -> dict:
    """
    Encuentra el slot (dia, hora) óptimo para una evaluación del equipo.

    Criterio de optimalidad (lexicográfico):
        1. Minimizar coste_total  (suma de penalizaciones)
        2. Minimizar peor_penalizacion  (minimax, desempate)
        3. Slot más temprano  (desempate final)

    Usa poda Branch & Bound: si el coste parcial ya supera al mejor
    conocido, se abandona ese slot sin terminar de calcularlo.

    Devuelve
    --------
    dict con:
        slot_optimo           – (dia, hora) o None
        dia_nombre            – nombre del día o None
        coste_total           – float
        peor_penalizacion     – float
        detalle_por_profesor  – list[dict]
        sin_solucion          – bool
        candidatos_evaluados  – int
    """
    # Si no hay índices construidos aún (primera vez sin PDF), devolver vacío
    if not indices or not equipo_educativo:
        return _sin_solucion("No hay datos o el equipo educativo está vacío.")

    equipo = list(equipo_educativo)
    slots  = indices.get("slots_calendario", [])

    # ── Generar candidatos libres ────────────────────────────────────────────
    ocupado = indices.get("ocupado", {})
    candidatos = [
        slot for slot in slots
        if all(slot not in ocupado.get(pid, set()) for pid in equipo)
    ]

    if not candidatos:
        return _sin_solucion(
            "No existe ningún slot libre común para todos los profesores del equipo.",
            bloqueados=_analizar_bloqueos(slots, equipo, ocupado),
        )

    # ── Ordenar heurísticamente (sesiones centrales primero) ────────────────
    # Esto permite encontrar pronto una buena solución y podar más agresivamente
    sesiones_validas = indices.get("sesiones_validas", [1,2,3,4,5,6])
    centro = (min(sesiones_validas) + max(sesiones_validas)) / 2
    candidatos.sort(key=lambda s: (abs(s[1] - centro), s[0], s[1]))

    # ── Backtracking con Branch & Bound ─────────────────────────────────────
    mejor_coste     = float("inf")
    mejor_peor      = float("inf")
    mejor_slot      = None
    mejor_detalle   = []

    for dia, hora in candidatos:
        suma_parcial = 0.0
        max_parcial  = 0.0
        detalle_slot = []
        poda         = False

        for pid in equipo:
            pen = penalizacion(pid, dia, hora, indices)
            suma_parcial += pen
            max_parcial   = max(max_parcial, pen)

            # ── PODA ────────────────────────────────────────────────────────
            # Si ya superamos el mejor coste total → no puede mejorar
            if suma_parcial > mejor_coste:
                poda = True
                break
            # Si empatamos en coste pero la peor pen ya es >= → tampoco mejora
            if suma_parcial == mejor_coste and max_parcial >= mejor_peor:
                poda = True
                break

            # Acumular detalle para la salida
            horas_dia = indices["ocupado_por_dia"].get(pid, {}).get(dia, [])
            cercana   = _hora_mas_cercana(hora, horas_dia)
            detalle_slot.append({
                "profesor_id":             pid,
                "penalizacion":            pen,
                "sesion_ocupada_cercana":  cercana,
                "tiene_sesiones_ese_dia":  bool(horas_dia),
            })

        if poda:
            continue

        # ── Criterio lexicográfico ───────────────────────────────────────────
        orden_temporal = dia * 10 + hora   # número creciente día/hora
        mejor_orden    = (mejor_slot[0] * 10 + mejor_slot[1]) if mejor_slot else float("inf")

        if (suma_parcial, max_parcial, orden_temporal) < (mejor_coste, mejor_peor, mejor_orden):
            mejor_coste   = suma_parcial
            mejor_peor    = max_parcial
            mejor_slot    = (dia, hora)
            mejor_detalle = detalle_slot

    if mejor_slot is None:
        return _sin_solucion("Todos los candidatos fueron podados (sin solución viable).")

    return {
        "sin_solucion":          False,
        "slot_optimo":           mejor_slot,
        "dia_nombre":            DIAS_NOMBRE[mejor_slot[0]],
        "hora_sesion":           mejor_slot[1],
        "coste_total":           round(mejor_coste, 2),
        "peor_penalizacion":     round(mejor_peor, 2),
        "detalle_por_profesor":  mejor_detalle,
        "num_candidatos":        len(candidatos),
        "grupo_objetivo":        grupo_objetivo,
        "equipo_size":           len(equipo),
        "mensaje":               (
            f"✅ Slot óptimo encontrado: {DIAS_NOMBRE[mejor_slot[0]]}, "
            f"sesión {mejor_slot[1]}. "
            f"Coste total: {round(mejor_coste, 2)} | "
            f"Peor penalización: {round(mejor_peor, 2)}"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS INTERNOS
# ─────────────────────────────────────────────────────────────────────────────

def _hora_mas_cercana(hora: int, horas_ocupadas: list) -> Optional[int]:
    """Devuelve la hora ocupada más cercana a 'hora' usando búsqueda binaria."""
    if not horas_ocupadas:
        return None
    pos = bisect_left(horas_ocupadas, hora)
    candidatos = []
    if pos < len(horas_ocupadas):
        candidatos.append(horas_ocupadas[pos])
    if pos > 0:
        candidatos.append(horas_ocupadas[pos - 1])
    return min(candidatos, key=lambda h: abs(h - hora))


def _sin_solucion(mensaje: str, bloqueados: Optional[dict] = None) -> dict:
    return {
        "sin_solucion":         True,
        "slot_optimo":          None,
        "dia_nombre":           None,
        "hora_sesion":          None,
        "coste_total":          None,
        "peor_penalizacion":    None,
        "detalle_por_profesor": [],
        "num_candidatos":       0,
        "grupo_objetivo":       None,
        "equipo_size":          0,
        "mensaje":              mensaje,
        "bloqueos_por_slot":    bloqueados or {},
    }


def _analizar_bloqueos(slots: list, equipo: list, ocupado: dict) -> dict:
    """Para diagnóstico: cuántos profesores bloquean cada slot."""
    return {
        f"{DIAS_NOMBRE[d]}-S{h}": sum(
            1 for pid in equipo if (d, h) in ocupado.get(pid, set())
        )
        for d, h in slots
    }