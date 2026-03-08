from flask import Blueprint, render_template, request
import re

horarios_bp = Blueprint('horarios', __name__)

# ─────────────────────────────────────────────────────────────────────────────
#  CLASIFICADOR DE GRUPOS
# ─────────────────────────────────────────────────────────────────────────────

def clasificar_grupo(g):
    """Devuelve el nivel de un grupo: ESO, BACH, 1FP, 2FP, OTROS."""
    g = g.strip()
    if re.match(r'^E[1-4][A-Z]', g) or g.startswith('DIV'):
        return 'ESO'
    if re.match(r'^B[12]', g):
        return 'BACH'
    if re.match(r'^1[A-Z]', g):
        return '1FP'
    if re.match(r'^2[A-Z]', g):
        return '2FP'
    if g.startswith('BIG') or g.startswith('Bil'):
        return 'FP SUP'
    return 'OTROS'

NIVEL_ORDEN = ['ESO', 'BACH', '1FP', '2FP', 'FP SUP', 'OTROS']
NIVEL_LABELS = {
    'ESO':    '📚 ESO',
    'BACH':   '🎓 Bachillerato',
    '1FP':    '🔧 1º FP',
    '2FP':    '🏆 2º FP',
    'FP SUP': '🚀 FP Superior / BIG',
    'OTROS':  '📋 Otros grupos',
}

# Grupos que son tareas internas (no alumnos reales) — se excluyen del desplegable
_EXCLUIDOS = {
    'G. MAÑANA', 'G. MAÑANA BIBLIOTECA', 'G. TARDE',
    'RDP', 'CCP', 'CERO', 'CIB', 'PYT', 'VIR',
    'REEQD', 'REEQ_ESO_BACH', 'REEQ_FP',
}

def grupos_por_nivel(datos_profesores: dict) -> dict:
    """
    Devuelve dict {nivel: [grupos_ordenados]} a partir de datos_profesores.
    Filtra grupos internos y los clasifica por nivel.
    """
    todos = set()
    for sesiones in datos_profesores.values():
        for s in sesiones:
            g = s.get('grupo_principal', '-')
            if g and g != '-' and g not in _EXCLUIDOS:
                # También excluir strings con "Tutores" (son reuniones)
                if not g.startswith('Tutores') and not g.startswith('Bil '):
                    todos.add(g)

    agrupados = {n: [] for n in NIVEL_ORDEN}
    for g in sorted(todos):
        nivel = clasificar_grupo(g)
        agrupados[nivel].append(g)

    return {n: gs for n, gs in agrupados.items() if gs}


# ─────────────────────────────────────────────────────────────────────────────
#  LÓGICA PRINCIPAL (placeholder hasta que el compañero entregue el backtracking)
# ─────────────────────────────────────────────────────────────────────────────

def find_best_meeting_slot(indices, equipo_educativo, config):
    """Stub — sustituir por el algoritmo real de backtracking."""
    return {
        "slot_optimo": None,
        "coste_total": None,
        "peor_penalizacion": None,
        "detalle_por_profesor": [],
        "sin_solucion": True,
        "mensaje": "⏳ Algoritmo de backtracking pendiente de implementar.",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  RUTAS
# ─────────────────────────────────────────────────────────────────────────────

@horarios_bp.route('/calcular', methods=['GET', 'POST'])
def calcular():
    # Importación diferida para evitar circular imports
    from subir_pdf import datos_profesores

    grupos = grupos_por_nivel(datos_profesores)
    hay_datos = bool(datos_profesores)

    if request.method == 'GET':
        return render_template(
            'generar_horario.html',
            grupos_por_nivel=grupos,
            nivel_labels=NIVEL_LABELS,
            hay_datos=hay_datos,
        )

    # ── POST: recoger filtros y ejecutar algoritmo ───────────────────────────
    grupo_objetivo = request.form.get('grupo_objetivo', '').strip()

    config = {
        # Requisito 1: horas no lectivas válidas para evaluación
        'horas_no_lectivas_validas': request.form.getlist('horas_no_lectivas'),

        # Requisito 2: número de días disponibles por nivel
        'dias_por_nivel': {
            'ESO':    int(request.form.get('dias_eso',  5)),
            'BACH':   int(request.form.get('dias_bach', 5)),
            '1FP':    int(request.form.get('dias_1fp',  5)),
            '2FP':    int(request.form.get('dias_2fp',  5)),
            'FP SUP': int(request.form.get('dias_sup',  5)),
        },

        # Requisito 3: permitir 7ª hora
        'permitir_septima': request.form.get('permitir_septima') == 'on',

        # Requisito 4: permitir recreo
        'permitir_recreo': request.form.get('permitir_recreo') == 'on',
    }

    # Construir equipo educativo y ejecutar algoritmo
    from subir_pdf import get_horario_global
    horario_global = get_horario_global()

    equipo = {s['profesor_id'] for s in horario_global
              if s['grupo'].split('-')[0].strip() == grupo_objetivo}

    resultado = find_best_meeting_slot({}, equipo, config)
    resultado['grupo_objetivo'] = grupo_objetivo
    resultado['config'] = config
    resultado['equipo_size'] = len(equipo)

    return render_template('resultado.html', datos=resultado)
