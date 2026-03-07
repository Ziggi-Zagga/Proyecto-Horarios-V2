# =============================================================================
# config.py
# -----------------------------------------------------------------------------
# Central configuration for the timetable optimiser.
# All tunable constants live here so that the rest of the code never contains
# "magic numbers".  Change values here and every module picks them up.
# =============================================================================


# ---------------------------------------------------------------------------
# CALENDAR
# ---------------------------------------------------------------------------

# Days of the week in use (0 = Monday … 4 = Friday)
DIAS_VALIDOS: list[int] = [0, 1, 2, 3, 4]

# Human-readable day names
NOMBRES_DIAS: dict[int, str] = {
    0: "Lunes",
    1: "Martes",
    2: "Miércoles",
    3: "Jueves",
    4: "Viernes",
}

# Total number of sessions per day
NUM_SESIONES: int = 7

# Recess hour
HORA_RECREO: int | None = 4


# ---------------------------------------------------------------------------
# SESSION POLICY
# ---------------------------------------------------------------------------

PERMITIR_SESION_7: bool = True
PERMITIR_RECREO: bool = False
PERMITIR_HORAS_SIN_CLASE: bool = True


# ---------------------------------------------------------------------------
# VALID SESSIONS
# ---------------------------------------------------------------------------

def _build_sesiones_validas() -> list[int]:

    sesiones = list(range(1, NUM_SESIONES + 1))

    if not PERMITIR_RECREO and HORA_RECREO is not None:
        sesiones = [s for s in sesiones if s != HORA_RECREO]

    if not PERMITIR_SESION_7:
        sesiones = [s for s in sesiones if s != 7]

    return sesiones


SESIONES_VALIDAS: list[int] = _build_sesiones_validas()


SLOTS_CALENDARIO: list[tuple[int, int]] = [
    (dia, hora)
    for dia in DIAS_VALIDOS
    for hora in SESIONES_VALIDAS
]


# ---------------------------------------------------------------------------
# PENALTIES
# ---------------------------------------------------------------------------

PENALIZACION_DIA_LIBRE: int = 7


# ---------------------------------------------------------------------------
# LEVEL CONFIGURATION
# ---------------------------------------------------------------------------

DIAS_EVALUACION: dict[str, int] = {
    "ESO": 1,
    "BACH": 1,
    "FP": 2,
}


# ---------------------------------------------------------------------------
# UPLOAD CONFIGURATION
# ---------------------------------------------------------------------------

# ⚠️ AQUÍ ESTABA EL PROBLEMA
# ahora se permiten PDFs

EXTENSIONES_PERMITIDAS: set[str] = {"pdf", "json", "csv"}

# Maximum upload size
MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# FIELD VALIDATION
# ---------------------------------------------------------------------------

CAMPOS_REQUERIDOS: list[str] = [
    "profesor_id",
    "dia",
    "hora",
    "grupo",
]

CAMPOS_OPCIONALES: list[str] = [
    "tarea",
    "aula",
]