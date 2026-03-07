from flask import Blueprint, render_template, request, flash, redirect, url_for
import pdfplumber
import re

subir_pdfs_bp = Blueprint('subir_pdfs', __name__)

datos_profesores = {}


def limpiar_texto(texto):
    """Limpia caracteres extraños del PDF"""
    if not texto: return ""
    texto = str(texto)
    texto = re.sub(r'\(cid:\d+\)', '', texto)
    texto = texto.replace('~', '-')
    return texto.strip()


def es_tarea_independiente(tarea):
    """Identifica si una tarea no necesita grupo (reuniones, guardias, etc)"""
    t = tarea.upper()
    return any(x in t for x in ["1104", "REUNIÓN", "REUNION", "GUARDIA", "RECREO", "CERO", "BUS"])


def extraer_datos_profesor(pagina, num_pagina):
    horario_profesor = []

    # Estrategia geométrica estricta
    tablas = pagina.extract_tables({
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines"
    })

    if not tablas:
        return horario_profesor

    tabla = tablas[0]  # Cogemos solo la tabla principal para omitir la basura del final
    patron_hora = re.compile(r'\d{1,2}:\d{2}')

    # 1. MAPEO DE DÍAS (Evita que el Jueves y Viernes se desplacen)
    dias_indices = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5}

    for fila in tabla[:5]:
        encontrados = 0
        temp_indices = {}
        for i, celda in enumerate(fila):
            texto = limpiar_texto(celda).upper()
            if "LUNES" in texto:
                temp_indices[0] = i; encontrados += 1
            elif "MARTES" in texto:
                temp_indices[1] = i; encontrados += 1
            elif "MIÉRCOLES" in texto or "MIERCOLES" in texto:
                temp_indices[2] = i; encontrados += 1
            elif "JUEVES" in texto:
                temp_indices[3] = i; encontrados += 1
            elif "VIERNES" in texto:
                temp_indices[4] = i; encontrados += 1

        if encontrados >= 3:
            dias_indices.update(temp_indices)
            break

    estado_dias = {0: None, 1: None, 2: None, 3: None, 4: None}

    for fila in tabla:
        if len(fila) == 0: continue

        hora_texto = limpiar_texto(fila[0])

        # Fin del horario, empieza la leyenda
        if "Periodos" in hora_texto or "Lectivas" in hora_texto or "Materias" in hora_texto:
            break

        if not patron_hora.search(hora_texto):
            continue

        hora_limpia = hora_texto.replace('\n', ' a ')

        # 2. EL RECREO
        es_recreo_fila = "11:00" in hora_limpia and "11:30" in hora_limpia
        if es_recreo_fila:
            for dia_num in range(5):
                horario_profesor.append({
                    "dia": dia_num,
                    "hora_original": hora_limpia,
                    "tarea": "☕ RECREO",
                    "grupo": "-",
                    "aula": "-"
                })
                estado_dias[dia_num] = None
            continue

        # 3. EXTRACCIÓN Y FUSIÓN DE HORAS
        for dia_num in range(5):
            col_idx = dias_indices.get(dia_num)
            celda = fila[col_idx] if (col_idx is not None and col_idx < len(fila)) else None

            # --- A. Fusión Geométrica (El PDF dice literalmente que es la misma caja) ---
            if celda is None:
                if estado_dias[dia_num] is not None:
                    clase_ant = estado_dias[dia_num]
                    hora_inicio = clase_ant["hora_original"].split(' a ')[0]
                    hora_fin = hora_limpia.split(' a ')[1] if ' a ' in hora_limpia else hora_limpia
                    clase_ant["hora_original"] = f"{hora_inicio} a {hora_fin}"
                continue

            texto_celda = limpiar_texto(celda)

            # --- B. Hueco Libre ---
            if texto_celda == "":
                estado_dias[dia_num] = None
                continue

            lineas = [L.strip() for L in texto_celda.split('\n') if L.strip()]
            if not lineas:
                estado_dias[dia_num] = None
                continue

            # Detectamos los elementos
            tarea = lineas[0]
            grupo = lineas[1] if len(lineas) > 1 else "Sin grupo"
            aula = lineas[2] if len(lineas) > 2 else "Sin aula"

            if "recreo" in texto_celda.lower():
                tarea, grupo, aula = "☕ RECREO", "-", "-"

            # --- C. Fusión Inteligente (El texto se ha partido a la mitad) ---
            merged = False
            if estado_dias[dia_num] is not None:
                clase_ant = estado_dias[dia_num]

                # Regla 1: Son clases idénticas en horas seguidas
                es_misma_clase = (clase_ant["tarea"] == tarea and clase_ant["grupo"] == grupo)

                # Regla 2: El texto se cortó (arriba Asignatura, abajo el Grupo)
                es_mitad_abajo = (
                        clase_ant["grupo"] == "Sin grupo"
                        and not es_tarea_independiente(clase_ant["tarea"])  # Impide fusionar "1104-CTVP" con "Lengua"
                )

                if es_misma_clase or es_mitad_abajo:
                    # Actualizamos la hora sumando las dos
                    hora_inicio = clase_ant["hora_original"].split(' a ')[0]
                    hora_fin = hora_limpia.split(' a ')[1] if ' a ' in hora_limpia else hora_limpia
                    clase_ant["hora_original"] = f"{hora_inicio} a {hora_fin}"

                    if es_mitad_abajo:
                        # Recuperamos el grupo y el aula que se habían quedado en la celda de abajo
                        clase_ant["grupo"] = lineas[0] if len(lineas) > 0 else clase_ant["grupo"]
                        clase_ant["aula"] = lineas[1] if len(lineas) > 1 else clase_ant["aula"]

                    merged = True

            if merged:
                continue  # Como lo hemos fusionado, no creamos una clase nueva

            # --- D. Crear nueva clase ---
            nueva_clase = {
                "dia": dia_num,
                "hora_original": hora_limpia,
                "tarea": tarea,
                "grupo": grupo,
                "aula": aula
            }

            horario_profesor.append(nueva_clase)
            estado_dias[dia_num] = nueva_clase

    return horario_profesor


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
                datos = extraer_datos_profesor(pagina, num_pagina)
                datos_profesores[profesor_id] = datos

        return redirect(url_for('subir_pdfs.lista_profesores'))
    else:
        flash('Por favor, sube un PDF válido.')
        return redirect(url_for('subir_pdf'))


@subir_pdfs_bp.route('/profesores')
def lista_profesores():
    return render_template('profesores.html', profesores=datos_profesores.keys())


@subir_pdfs_bp.route('/profesor/<profesor_id>')
def detalle_profesor(profesor_id):
    sesiones = datos_profesores.get(profesor_id, [])
    dias_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes']
    horario_agrupado = {dia: [] for dia in dias_semana}

    for sesion in sesiones:
        nombre_dia = dias_semana[sesion['dia']]
        horario_agrupado[nombre_dia].append({
            "hora": sesion['hora_original'],
            "tarea": sesion['tarea'],
            "grupo": sesion['grupo'],
            "aula": sesion['aula']
        })

    return render_template('profesor_detalle.html', profesor_id=profesor_id, horario_agrupado=horario_agrupado)