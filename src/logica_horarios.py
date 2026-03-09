from flask import Blueprint, render_template, request
import re

horarios_bp = Blueprint('horarios', __name__)


# ─────────────────────────────────────────────────────────────────────────────
#  CLASIFICADOR DE GRUPOS
# ─────────────────────────────────────────────────────────────────────────────

def clasificar_grupo(g):
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

NIVEL_ORDEN  = ['ESO', 'BACH', '1FP', '2FP', 'FP SUP', 'OTROS']
NIVEL_LABELS = {
    'ESO':    '📚 ESO',
    'BACH':   '🎓 Bachillerato',
    '1FP':    '🔧 1º FP',
    '2FP':    '🏆 2º FP',
    'FP SUP': '🚀 FP Superior / BIG',
    'OTROS':  '📋 Otros grupos',
}

_EXCLUIDOS = {
    'G. MAÑANA', 'G. MAÑANA BIBLIOTECA', 'G. TARDE',
    'RDP', 'CCP', 'CERO', 'CIB', 'PYT', 'VIR',
    'REEQD', 'REEQ_ESO_BACH', 'REEQ_FP',
}

def grupos_por_nivel(datos_profesores: dict) -> dict:
    todos = set()
    for sesiones in datos_profesores.values():
        for s in sesiones:
            g = s.get('grupo_principal', '-')
            if g and g != '-' and g not in _EXCLUIDOS:
                if not g.startswith('Tutores') and not g.startswith('Bil '):
                    todos.add(g)

    agrupados = {n: [] for n in NIVEL_ORDEN}
    for g in sorted(todos):
        nivel = clasificar_grupo(g)
        agrupados[nivel].append(g)

    return {n: gs for n, gs in agrupados.items() if gs}


# ─────────────────────────────────────────────────────────────────────────────
#  RUTAS
# ─────────────────────────────────────────────────────────────────────────────

@horarios_bp.route('/calcular', methods=['POST'])
def calcular():
    from src.subir_pdfs import datos_profesores, get_horario_global
    from src.algoritmo_backtracking import build_indices, get_team_for_group, find_best_meeting_slot

    grupo_objetivo = request.form.get('grupo_objetivo', '').strip()

    # ── Construir config desde el formulario ────────────────────────────────
    config = {
        'horas_no_lectivas_libres': request.form.getlist('horas_no_lectivas'),
        'permitir_ultima_hora':      request.form.get('permitir_septima') == 'on',
        'permitir_recreo':          request.form.get('permitir_recreo') == 'on',
        'dias_validos':             list(range(5)),
    }

    # Días disponibles por nivel: si el grupo tiene un nivel con menos días,
    # recortamos dias_validos a los N primeros (Lunes … N-1)
    nivel_grupo = clasificar_grupo(grupo_objetivo)
    campo_dias  = {
        'ESO': 'dias_eso', 'BACH': 'dias_bach',
        '1FP': 'dias_1fp', '2FP': 'dias_2fp', 'FP SUP': 'dias_sup',
    }
    campo = campo_dias.get(nivel_grupo)
    if campo:
        n_dias = int(request.form.get(campo, 5))
        config['dias_validos'] = list(range(min(n_dias, 5)))

    # ── Ejecutar algoritmo ───────────────────────────────────────────────────
    horario_global = get_horario_global()
    equipo         = get_team_for_group(horario_global, grupo_objetivo)
    indices        = build_indices(horario_global, config)
    resultado      = find_best_meeting_slot(indices, equipo, config, grupo_objetivo)

    return render_template('resultado.html', datos=resultado)