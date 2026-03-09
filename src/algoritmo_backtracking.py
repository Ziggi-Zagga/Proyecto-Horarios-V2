"""
algoritmo_backtracking.py  — v2 (franjas horarias reales)
─────────────────────────────────────────────────────────────────────────────
Trabaja con franjas reales (hora_inicio, hora_fin) en lugar de números de
sesión, porque el centro tiene turnos de mañana, tarde y partido, con
distinto número de recreos cada uno.

Franjas lectivas estándar (55 min):
  Mañana:  08:15, 09:10, 10:05, 11:30, 12:25, 13:20
  Mediodía: 14:25
  Tarde:   15:20, 16:15, 17:10, 18:35, 19:30, 20:25
  Especial: 07:45 (30 min)

Recreos fijos (excluidos siempre de candidatos):
  11:00–11:30 · 14:15–14:25 · 18:05–18:35

Interfaz pública:
  build_indices(horario, config)          → indices
  get_team_for_group(horario, grupo)      → set[profesor_id]
  find_best_meeting_slot(indices, equipo, config, grupo) → resultado
"""

from bisect import bisect_left
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
#  DEFINICIÓN DE FRANJAS Y RECREOS
# ─────────────────────────────────────────────────────────────────────────────

# Todas las franjas del centro en orden cronológico (lectivas + recreos)
# Tupla: (hora_ini, hora_fin, es_recreo)
FRANJAS_ESTANDAR = [
    ("07:45", "08:15", False),   # especial 30 min
    ("08:15", "09:10", False),
    ("09:10", "10:05", False),
    ("10:05", "11:00", False),
    ("11:00", "11:30", True),    # recreo 1
    ("11:30", "12:25", False),
    ("12:25", "13:20", False),
    ("13:20", "14:15", False),
    ("14:15", "14:25", True),    # recreo 2
    ("14:25", "15:20", False),
    ("15:20", "16:15", False),
    ("16:15", "17:10", False),
    ("17:10", "18:05", False),
    ("18:05", "18:35", True),    # recreo 3
    ("18:35", "19:30", False),
    ("19:30", "20:25", False),
    ("20:25", "21:20", False),   # "última hora" de tarde
]
RECREOS_INICIO = {ini for ini, fin, es_rec in FRANJAS_ESTANDAR if es_rec}

# Franja "última hora" de tarde
ULTIMA_HORA_INI = "20:25"

# Penalización máxima (profesor sin sesiones ese día)
# Equivale a estar "a todo un día de distancia" = 7 sesiones × 55 min
PEN_SIN_SESIONES = 385   # minutos

DIAS_NOMBRE = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes"}


def t2m(hora: str) -> int:
    """'HH:MM' → minutos desde medianoche."""
    h, m = map(int, hora.split(":"))
    return h * 60 + m


# ─────────────────────────────────────────────────────────────────────────────
#  PASO 1 — CONSTRUCCIÓN DE ÍNDICES
# ─────────────────────────────────────────────────────────────────────────────

def build_indices(horario: list[dict], config: dict) -> dict:
    """
    Construye las estructuras internas del algoritmo a partir de la lista
    plana de sesiones (salida de get_horario_global).

    config admite:
      permitir_recreo      bool  – si True, los recreos son candidatos
      permitir_ultima_hora bool  – si True, la franja 20:25-21:20 es candidata
      horas_no_lectivas_libres list[str] – tareas que cuentan como libres
      dias_validos         list[int]    – días candidatos (0=Lunes…4=Viernes)
    """
    permitir_recreo  = config.get("permitir_recreo", False)
    # compatibilidad con nombre anterior "permitir_septima"
    permitir_ultima  = config.get("permitir_ultima_hora",
                                  config.get("permitir_septima", False))
    dias_validos     = config.get("dias_validos", list(range(5)))
    nl_libres        = {t.upper() for t in config.get("horas_no_lectivas_libres", [])}

    # ── Franjas candidatas ───────────────────────────────────────────────────
    franjas_candidatas = []
    for ini, fin, es_recreo in FRANJAS_ESTANDAR:
        if es_recreo and not permitir_recreo:
            continue
        if ini == ULTIMA_HORA_INI and not permitir_ultima:
            continue
        # excluir 07:45 (guardia especial de media hora)
        if ini == "07:45":
            continue
        franjas_candidatas.append((ini, fin))

    # ── Slots del calendario ─────────────────────────────────────────────────
    slots_calendario = [
        (dia, ini, fin)
        for dia in dias_validos
        for ini, fin in franjas_candidatas
    ]

    # ── Índices de ocupación (en minutos) ────────────────────────────────────
    # Separamos dos índices con propósitos distintos:
    #
    # bloqueante_por_dia : sesiones que IMPIDEN usar ese slot como candidato.
    #   Solo incluye sesiones lectivas reales (excluye NL marcadas como libres).
    #
    # distancia_por_dia  : todas las sesiones, incluidas NL libres.
    #   Se usa para calcular la penalización (distancia al evento más cercano).
    #   El profesor sigue estando físicamente en el centro durante una guardia,
    #   por lo que un slot adyacente a ella no debería penalizarse como si
    #   estuviera "lejos" de su jornada.

    bloqueante_por_dia: dict[str, dict[int, list]] = {}
    distancia_por_dia:  dict[str, dict[int, list]] = {}

    for sesion in horario:
        pid   = sesion["profesor_id"]
        tarea = sesion.get("tarea", "").upper()

        ini_str = sesion.get("hora_inicio", "")
        fin_str = sesion.get("hora_fin", "")
        if not ini_str or not fin_str:
            continue

        dia = sesion.get("dia", -1)
        if isinstance(dia, str):
            dia_map = {"lunes":0,"martes":1,"miércoles":2,"miercoles":2,
                       "jueves":3,"viernes":4}
            dia = dia_map.get(dia.lower(), -1)
        if dia not in range(5):
            continue

        ini_m = t2m(ini_str)
        fin_m = t2m(fin_str)
        par   = (ini_m, fin_m)

        es_libre = any(nl in tarea for nl in nl_libres)

        # Distancia: siempre se añade (el prof está ahí de todas formas)
        distancia_por_dia.setdefault(pid, {}).setdefault(dia, [])
        if par not in distancia_por_dia[pid][dia]:
            distancia_por_dia[pid][dia].append(par)

        # Bloqueo: solo si NO es hora no lectiva libre
        if not es_libre:
            bloqueante_por_dia.setdefault(pid, {}).setdefault(dia, [])
            if par not in bloqueante_por_dia[pid][dia]:
                bloqueante_por_dia[pid][dia].append(par)

    # Ordenar por hora de inicio en ambos índices
    for idx_dict in (bloqueante_por_dia, distancia_por_dia):
        for pid in idx_dict:
            for dia in idx_dict[pid]:
                idx_dict[pid][dia].sort()

    return {
        "config":             config,
        "franjas_candidatas": franjas_candidatas,
        "slots_calendario":   slots_calendario,
        "bloqueante_por_dia": bloqueante_por_dia,
        "distancia_por_dia":  distancia_por_dia,
        # alias de compatibilidad (usado en penalizacion y overlaps)
        "ocupado_por_dia":    bloqueante_por_dia,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  PASO 2 — EQUIPO EDUCATIVO
# ─────────────────────────────────────────────────────────────────────────────

def get_team_for_group(horario: list[dict], grupo_objetivo: str) -> set:
    objetivo = grupo_objetivo.strip().upper()
    return {
        s["profesor_id"]
        for s in horario
        if s.get("grupo", "").strip().upper() == objetivo
    }


# ─────────────────────────────────────────────────────────────────────────────
#  PASO 3 — PENALIZACIÓN (en minutos)
# ─────────────────────────────────────────────────────────────────────────────

def _overlaps(ini_m: int, fin_m: int, sesiones_dia: list) -> bool:
    """True si el intervalo (ini_m, fin_m) solapa con alguna sesión del día."""
    for s_ini, s_fin in sesiones_dia:
        if ini_m < s_fin and fin_m > s_ini:
            return True
    return False


def penalizacion(pid: str, dia: int, slot_ini: str, slot_fin: str,
                 indices: dict) -> float:
    """
    Penalización del profesor 'pid' para el slot (dia, slot_ini, slot_fin).

    - Si no tiene sesiones ese día → PEN_SIN_SESIONES
    - Si el slot solapa con una sesión ocupada → inf (no viable)
    - Si está libre → distancia en minutos al intervalo ocupado más cercano
    """
    # Para bloqueo: usamos bloqueante_por_dia (sin NL libres)
    bloq_dia  = indices.get("bloqueante_por_dia", indices.get("ocupado_por_dia", {}))
    ses_bloq  = bloq_dia.get(pid, {}).get(dia, [])

    # Para distancia: usamos distancia_por_dia (incluye NL libres)
    dist_dia  = indices.get("distancia_por_dia",  bloq_dia)
    ses_dist  = dist_dia.get(pid, {}).get(dia, [])

    slot_ini_m = t2m(slot_ini)
    slot_fin_m = t2m(slot_fin)

    # Solapamiento con sesión bloqueante → slot no viable
    if _overlaps(slot_ini_m, slot_fin_m, ses_bloq):
        return float("inf")

    # Sin ninguna sesión registrada ese día → penalización máxima
    if not ses_dist:
        return PEN_SIN_SESIONES

    # Distancia al intervalo más cercano (usando todas las sesiones como referencia)
    mejor = float("inf")
    for s_ini, s_fin in ses_dist:
        d = min(abs(slot_ini_m - s_fin), abs(s_ini - slot_fin_m))
        mejor = min(mejor, d)

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
    Encuentra el slot (dia, hora_inicio, hora_fin) óptimo.

    Criterio lexicográfico:
      1. coste_total mínimo (suma de penalizaciones en minutos)
      2. peor_penalizacion mínima (minimax)
      3. slot más temprano (lunes antes, mañana antes)

    Poda Branch & Bound: abandona un slot en cuanto el parcial supera al mejor.
    """
    if not indices or not equipo_educativo:
        return _sin_solucion("No hay datos o el equipo educativo está vacío.")

    equipo  = list(equipo_educativo)
    slots   = indices.get("slots_calendario", [])

    if not slots:
        return _sin_solucion("No hay franjas candidatas con la configuración actual.")

    # ── Candidatos libres: ningún profesor bloqueado en ese slot ─────────────
    # Usamos bloqueante_por_dia (excluye NL libres) para que una guardia
    # no impida proponer ese slot como candidato.
    bloq = indices.get("bloqueante_por_dia", indices.get("ocupado_por_dia", {}))
    candidatos = []
    for dia, ini, fin in slots:
        ini_m = t2m(ini)
        fin_m = t2m(fin)
        libre = True
        for pid in equipo:
            ses = bloq.get(pid, {}).get(dia, [])
            if _overlaps(ini_m, fin_m, ses):
                libre = False
                break
        if libre:
            candidatos.append((dia, ini, fin))

    if not candidatos:
        return _sin_solucion(
            "No existe ninguna franja libre común para todos los profesores del equipo."
        )

    # ── Ordenar heurísticamente: primero franjas centrales de mañana ─────────
    # Objetivo: encontrar pronto una buena solución → más poda
    CENTRO_M = t2m("11:00")   # centro aproximado de la mañana
    candidatos.sort(key=lambda s: (abs(t2m(s[1]) - CENTRO_M), s[0], t2m(s[1])))

    # ── Backtracking con Branch & Bound ─────────────────────────────────────
    mejor_coste   = float("inf")
    mejor_peor    = float("inf")
    mejor_slot    = None
    mejor_detalle = []

    for dia, ini, fin in candidatos:
        suma = 0.0
        maxi = 0.0
        detalle_slot = []
        poda = False

        for pid in equipo:
            pen = penalizacion(pid, dia, ini, fin, indices)

            if pen == float("inf"):       # bloqueado (no debería ocurrir aquí)
                poda = True; break

            suma += pen
            maxi  = max(maxi, pen)

            # ── PODA ────────────────────────────────────────────────────────
            if suma > mejor_coste:
                poda = True; break
            if suma == mejor_coste and maxi >= mejor_peor:
                poda = True; break

            # Calcular sesión cercana para el detalle
            ses_dia = indices["ocupado_por_dia"].get(pid, {}).get(dia, [])
            cercana = _intervalo_mas_cercano(t2m(ini), t2m(fin), ses_dia)
            detalle_slot.append({
                "profesor_id":            pid,
                "penalizacion_min":       round(pen),
                "intervalo_cercano":      cercana,       # (ini_str, fin_str) o None
                "tiene_sesiones_ese_dia": bool(ses_dia),
            })

        if poda:
            continue

        # ── Criterio lexicográfico ───────────────────────────────────────────
        orden = (dia, t2m(ini))
        mejor_orden = (mejor_slot[0], t2m(mejor_slot[1])) if mejor_slot else (99, 9999)

        if (suma, maxi, orden) < (mejor_coste, mejor_peor, mejor_orden):
            mejor_coste   = suma
            mejor_peor    = maxi
            mejor_slot    = (dia, ini, fin)
            mejor_detalle = detalle_slot

    if mejor_slot is None:
        return _sin_solucion("Todos los candidatos fueron descartados por poda.")

    dia, ini, fin = mejor_slot
    return {
        "sin_solucion":          False,
        "slot_optimo":           mejor_slot,
        "dia":                   dia,
        "dia_nombre":            DIAS_NOMBRE[dia],
        "hora_inicio":           ini,
        "hora_fin":              fin,
        "hora_display":          f"{ini} – {fin}",
        "coste_total":           round(mejor_coste),
        "peor_penalizacion":     round(mejor_peor),
        "detalle_por_profesor":  mejor_detalle,
        "num_candidatos":        len(candidatos),
        "grupo_objetivo":        grupo_objetivo,
        "equipo_size":           len(equipo),
        "mensaje": (
            f"✅ Slot óptimo: {DIAS_NOMBRE[dia]} {ini}–{fin}. "
            f"Coste total: {round(mejor_coste)} min | "
            f"Peor penalización: {round(mejor_peor)} min"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def m2t(m: int) -> str:
    """Minutos desde medianoche → 'HH:MM'."""
    return f"{m // 60:02d}:{m % 60:02d}"


def _intervalo_mas_cercano(slot_ini_m: int, slot_fin_m: int,
                           sesiones_dia: list) -> Optional[tuple]:
    """Devuelve el intervalo (ini_str, fin_str) más cercano al slot."""
    if not sesiones_dia:
        return None
    mejor_d = float("inf")
    mejor   = None
    for s_ini, s_fin in sesiones_dia:
        d = min(abs(slot_ini_m - s_fin), abs(s_ini - slot_fin_m))
        if d < mejor_d:
            mejor_d = d
            mejor   = (m2t(s_ini), m2t(s_fin))
    return mejor


def _sin_solucion(mensaje: str) -> dict:
    return {
        "sin_solucion":          True,
        "slot_optimo":           None,
        "dia":                   None,
        "dia_nombre":            None,
        "hora_inicio":           None,
        "hora_fin":              None,
        "hora_display":          None,
        "coste_total":           None,
        "peor_penalizacion":     None,
        "detalle_por_profesor":  [],
        "num_candidatos":        0,
        "grupo_objetivo":        None,
        "equipo_size":           0,
        "mensaje":               mensaje,
    }