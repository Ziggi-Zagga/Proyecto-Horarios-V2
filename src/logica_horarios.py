from flask import Blueprint, render_template

# Creamos el Blueprint llamado 'horarios_bp'
horarios_bp = ('horarios', __name__)


# Simulación de la función del algoritmo que hará tu compañero de Backtracking
def find_best_meeting_slot(indices, equipo_educativo, config):
    # Aquí en el futuro importará y llamará al código real de backtracking
    return {
        "slot_optimo": "Miércoles - 3ª Hora",
        "coste_total": 12,
        "peor_penalizacion": 4,
        "detalle_por_profesor": [],
        "sin_solucion": False,
        "mensaje": "¡Conectado desde src/logica_horarios.py con éxito!"
    }


# Fíjate que usamos @horarios_bp en lugar de @app
@horarios_bp.route('/calcular')
def calcular():
    # Simulamos variables vacías por ahora
    indices_falsos = {}
    equipo_falso = set()
    config_falsa = {}

    # Llamamos al algoritmo
    resultado = find_best_meeting_slot(indices_falsos, equipo_falso, config_falsa)

    # Renderizamos la plantilla de la carpeta web/templates
    return render_template('resultado.html', datos=resultado)