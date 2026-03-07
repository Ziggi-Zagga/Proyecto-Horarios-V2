from flask import Blueprint, render_template, request, flash, redirect, url_for
import pdfplumber
import re

subir_pdfs_bp = Blueprint('subir_pdfs', __name__)

datos_profesores = {}   # profesor_id -> list[dict sesión]


# ─────────────────────────────────────────────────────────────────────────────
#  UTILIDADES
# ─────────────────────────────────────────────────────────────────────────────

def limpiar_texto(texto):
    if not texto:
        return ""
    texto = re.sub(r'\(cid:\d+\)', '', str(texto))
    texto = texto.replace('~', '-')
    return texto.strip()


# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

DIA_MAP    = {'LUNES': 0, 'MARTES': 1, 'MIÉRCOLES': 2,
              'MIERCOLES': 2, 'JUEVES': 3, 'VIERNES': 4}
DIA_NOMBRE = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves', 4: 'Viernes'}
PAT_HORA   = re.compile(r'^\d{1,2}:\d{2}$')


# ─────────────────────────────────────────────────────────────────────────────
#  EXTRACCIÓN GEOMÉTRICA
#
#  PRINCIPIO CLAVE:
#    - Las celdas VACÍAS no generan rectángulo propio; solo se ve el fondo crema.
#    - Las celdas OCUPADAS siempre tienen su propio rectángulo con texto,
#      independientemente del color (naranja, azul, gris, amarillo...).
#    - Por tanto: filtramos por GEOMETRÍA, no por color.
# ─────────────────────────────────────────────────────────────────────────────

def extraer_datos_profesor(pagina, num_pagina):
    sesiones = []
    words = pagina.extract_words()
    rects = pagina.rects

    # ── 1. Columnas de días ──────────────────────────────────────────────────
    dia_centros = {}
    for w in words:
        k = limpiar_texto(w['text']).upper()
        if k in DIA_MAP and DIA_MAP[k] not in dia_centros:
            dia_centros[DIA_MAP[k]] = (w['x0'] + w['x1']) / 2

    if len(dia_centros) < 2:
        return sesiones

    # Marco grande del horario
    candidatos = [r for r in rects
                  if r['x1'] - r['x0'] > 400 and r['bottom'] - r['top'] > 200]
    if not candidatos:
        return sesiones
    marco = sorted(candidatos, key=lambda r: -(r['x1'] - r['x0']))[0]

    borde_izq = marco['x0'] + 40
    borde_der = marco['x1']
    n_dias    = len(dia_centros)
    ancho_col = (borde_der - borde_izq) / n_dias

    dia_limites = {}
    for i, d in enumerate(sorted(dia_centros)):
        dia_limites[d] = (borde_izq + i * ancho_col,
                          borde_izq + (i + 1) * ancho_col)

    # ── 2. Filas de sesiones ─────────────────────────────────────────────────
    col_x0 = marco['x0']
    col_x1 = col_x0 + 45

    hora_rects = sorted(
        [r for r in rects
         if r['x0'] <= col_x0 + 5 and r['x1'] <= col_x1 + 5
         and 15 <= r['bottom'] - r['top'] <= 130
         and r['top'] > marco['top'] + 5
         and r['bottom'] <= marco['bottom'] + 2],
        key=lambda r: r['top']
    )

    hw = [(w['text'], float(w['top'])) for w in words if PAT_HORA.match(w['text'])]

    filas = []
    sesion_num = 1
    for hr in hora_rects:
        horas_en = [h for h, t in hw if hr['top'] <= t <= hr['bottom']]
        if len(horas_en) >= 2:
            hi, hf = horas_en[0], horas_en[-1]
        elif len(horas_en) == 1:
            hi = hf = horas_en[0]
        else:
            continue

        # Recreo = existe rect de anchura total en esta misma fila
        es_recreo = any(
            r['x1'] - r['x0'] > 400 and abs(r['top'] - hr['top']) < 3
            for r in rects if r is not marco
        )

        filas.append({
            'top': hr['top'], 'bottom': hr['bottom'],
            'hi': hi, 'hf': hf,
            'es_recreo': es_recreo,
            'sesion_num': sesion_num if not es_recreo else None,
        })
        if not es_recreo:
            sesion_num += 1

    if not filas:
        return sesiones

    zona_top = filas[0]['top'] - 5
    # Usamos el borde inferior del MARCO, no de la última fila de la col de horas,
    # porque los rects de clase de la última sesión se extienden hasta el marco.
    zona_bot = marco['bottom']

    # ── 3. Celdas ocupadas: filtrado GEOMÉTRICO ──────────────────────────────
    #
    #  Una celda de clase cumple:
    #    a) x0 a la derecha de la columna de horas
    #    b) ancho <= ancho de una columna * 1.6  (no es el marco grande)
    #    c) altura > 15 px
    #    d) dentro de la zona horaria
    #    e) tiene texto no vacío  (celdas libres no generan rect propio)
    #
    umbral_x0 = marco['x0'] + 35
    max_ancho  = ancho_col * 1.6
    top_minimo = filas[0]['top'] - 3

    clase_rects = sorted(
        [r for r in rects
         if r['x0'] >= umbral_x0
         and r['x1'] - r['x0'] <= max_ancho
         and r['bottom'] - r['top'] > 15
         and r['top'] >= top_minimo
         and r['top'] <= zona_bot
         and r['bottom'] <= zona_bot + 10],
        key=lambda r: (r['top'], r['x0'])
    )

    for rect in clase_rects:
        cx = (rect['x0'] + rect['x1']) / 2

        # Determinar día
        dia_num = None
        for d, (xl, xr) in dia_limites.items():
            if xl - 5 <= rect['x0'] and rect['x1'] <= xr + 5:
                dia_num = d
                break
        if dia_num is None:
            for d, (xl, xr) in dia_limites.items():
                if xl <= cx <= xr:
                    dia_num = d
                    break
        if dia_num is None:
            continue

        # Sesiones cubiertas (sin recreo)
        filas_cub = [f for f in filas
                     if min(rect['bottom'], f['bottom']) - max(rect['top'], f['top']) > 10
                     and not f['es_recreo']]
        if not filas_cub:
            continue

        hora_inicio  = filas_cub[0]['hi']
        hora_fin     = filas_cub[-1]['hf']
        num_sesiones = len(filas_cub)
        sesion_num_i = filas_cub[0]['sesion_num']

        # Texto
        crop  = pagina.crop((rect['x0'], rect['top'], rect['x1'], rect['bottom']))
        txt   = limpiar_texto(crop.extract_text() or "")
        lineas = [l.strip() for l in txt.split('\n') if l.strip()]

        if not lineas:
            continue   # Celda vacía real (no debería ocurrir, pero por si acaso)

        tarea = lineas[0]
        grupo = lineas[1] if len(lineas) > 1 else "-"
        aula  = lineas[2] if len(lineas) > 2 else "-"

        if 'recreo' in tarea.lower():
            continue   # Algunas páginas tienen celdas de recreo individuales

        grupo_principal = grupo.split('-')[0].split(',')[0].strip() if grupo != "-" else "-"

        sesiones.append({
            'dia':             dia_num,
            'dia_nombre':      DIA_NOMBRE[dia_num],
            'hora_original':   f"{hora_inicio} a {hora_fin}",
            'hora_inicio':     hora_inicio,
            'hora_fin':        hora_fin,
            'num_sesiones':    num_sesiones,
            'sesion_num':      sesion_num_i,
            'tarea':           tarea,
            'grupo':           grupo,
            'grupo_principal': grupo_principal,
            'aula':            aula,
        })

    return sesiones


# ─────────────────────────────────────────────────────────────────────────────
#  RUTAS FLASK
# ─────────────────────────────────────────────────────────────────────────────

@subir_pdfs_bp.route('/procesar', methods=['POST'])
def procesar_subida():
    global datos_profesores
    datos_profesores.clear()

    if 'archivo' not in request.files:
        flash('No se ha subido ningún archivo')
        return redirect(url_for('subir_pdf'))

    archivo = request.files['archivo']

    if archivo and archivo.filename.endswith('.pdf'):
        with pdfplumber.open(archivo) as pdf:
            for num_pagina, pagina in enumerate(pdf.pages):
                profesor_id = f"Profesor {(num_pagina + 1):03d}"
                datos_profesores[profesor_id] = extraer_datos_profesor(pagina, num_pagina)
        return redirect(url_for('subir_pdfs.lista_profesores'))

    flash('Por favor, sube un PDF válido.')
    return redirect(url_for('subir_pdf'))


@subir_pdfs_bp.route('/profesores')
def lista_profesores():
    return render_template('profesores.html', profesores=datos_profesores.keys())


@subir_pdfs_bp.route('/profesor/<profesor_id>')
def detalle_profesor(profesor_id):
    sesiones = datos_profesores.get(profesor_id, [])
    horario_agrupado = {DIA_NOMBRE[d]: [] for d in range(5)}

    for sesion in sesiones:
        nombre_dia = DIA_NOMBRE.get(sesion['dia'], 'Desconocido')
        horario_agrupado[nombre_dia].append({
            "hora":         sesion['hora_original'],
            "tarea":        sesion['tarea'],
            "grupo":        sesion['grupo'],
            "aula":         sesion['aula'],
            "num_sesiones": sesion['num_sesiones'],
        })

    return render_template(
        'profesor_detalle.html',
        profesor_id=profesor_id,
        horario_agrupado=horario_agrupado,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  FUNCIÓN PÚBLICA PARA EL MÓDULO DE BACKTRACKING
# ─────────────────────────────────────────────────────────────────────────────

def get_horario_global():
    """
    Devuelve lista plana de sesiones para build_indices().
    Sesiones dobles/triples generan una entrada por cada hora lectiva.
    Campos: profesor_id, dia (0-4), hora (int), grupo, aula, tarea
    """
    horario = []
    for profesor_id, sesiones in datos_profesores.items():
        for s in sesiones:
            if s['sesion_num'] is None:
                continue
            for offset in range(s['num_sesiones']):
                horario.append({
                    'profesor_id': profesor_id,
                    'dia':         s['dia'],
                    'hora':        s['sesion_num'] + offset,
                    'grupo':       s['grupo_principal'],
                    'aula':        s['aula'],
                    'tarea':       s['tarea'],
                })
    return horario
