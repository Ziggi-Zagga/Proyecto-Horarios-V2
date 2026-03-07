# =============================================================================
# app.py
# Flask web application
# =============================================================================

from __future__ import annotations

import logging
import os
from functools import wraps

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from werkzeug.utils import secure_filename

from src.algoritmo import find_best_meeting_slot
from src.config import (
    EXTENSIONES_PERMITIDAS,
    MAX_UPLOAD_BYTES,
    NOMBRES_DIAS,
    SESIONES_VALIDAS,
)

from src.horarios import normalizar_entradas
from src.parser_csv import parsear_archivo
from src.parser_pdf import parsear_pdf_profesor


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Flask app
# -----------------------------------------------------------------------------

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)

app.secret_key = "horarios-secret"
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def requiere_horario(f):

    @wraps(f)
    def decorated(*args, **kwargs):

        if "horario" not in session:

            flash("Primero debes subir horarios.", "warning")

            return redirect(url_for("subir"))

        return f(*args, **kwargs)

    return decorated


def _allowed_file(filename: str):

    return "." in filename and filename.rsplit(".", 1)[1].lower() in EXTENSIONES_PERMITIDAS


# -----------------------------------------------------------------------------
# Context processor
# -----------------------------------------------------------------------------

@app.context_processor
def inject_globals():

    return {
        "nombres_dias": NOMBRES_DIAS,
        "sesiones_validas": SESIONES_VALIDAS,
    }


# -----------------------------------------------------------------------------
# Home
# -----------------------------------------------------------------------------

@app.route("/")
def index():

    return render_template("index.html")


# -----------------------------------------------------------------------------
# Subir archivos
# -----------------------------------------------------------------------------

@app.route("/subir", methods=["GET"])
def subir():

    return render_template("subir_pdf.html")


@app.route("/subir", methods=["POST"])
def subir_post():

    print("\n==============================")
    print("🚀 BOTÓN SUBIR PULSADO")
    print("==============================")

    if "archivo" not in request.files:

        flash("No se enviaron archivos.", "danger")
        return redirect(url_for("subir"))

    archivos = request.files.getlist("archivo")

    if not archivos:

        flash("Selecciona al menos un archivo.", "danger")
        return redirect(url_for("subir"))

    try:

        os.makedirs("uploads", exist_ok=True)

        todas_entradas = []

        for archivo in archivos:

            if archivo.filename == "":
                continue

            nombre = secure_filename(archivo.filename)

            if not _allowed_file(nombre):
                print("❌ extensión no permitida:", nombre)
                continue

            ruta = os.path.join("uploads", nombre)

            archivo.save(ruta)

            print("📄 PDF guardado:", ruta)

            # -----------------------------
            # PARSEAR ARCHIVO
            # -----------------------------

            if nombre.lower().endswith(".pdf"):

                entradas = parsear_pdf_profesor(ruta)

            else:

                with open(ruta, "rb") as f:
                    contenido = f.read()

                entradas = parsear_archivo(contenido, nombre)

            entradas_ok = normalizar_entradas(entradas)

            todas_entradas.extend(entradas_ok)

        print("📊 TOTAL ENTRADAS:", len(todas_entradas))

        if not todas_entradas:

            flash("No se pudo leer información de los PDFs.", "danger")
            return redirect(url_for("subir"))

        session["horario"] = todas_entradas
        session.pop("resultado", None)

        flash(f"{len(todas_entradas)} sesiones cargadas correctamente", "success")

        return redirect(url_for("generar"))

    except Exception as exc:

        logger.exception("Error procesando PDFs")

        flash(f"Error procesando archivos: {exc}", "danger")

        return redirect(url_for("subir"))


# -----------------------------------------------------------------------------
# Generar horario óptimo
# -----------------------------------------------------------------------------

@app.route("/generar", methods=["GET"])
@requiere_horario
def generar():

    entradas = normalizar_entradas(session["horario"])

    profesores = sorted(set(e["profesor_id"] for e in entradas))

    return render_template(
        "generar_horario.html",
        equipo=profesores
    )


@app.route("/generar", methods=["POST"])
@requiere_horario
def generar_post():

    profesores_seleccionados = request.form.getlist("profesores")

    entradas = normalizar_entradas(session["horario"])

    if profesores_seleccionados:

        entradas = [
            e for e in entradas
            if e["profesor_id"] in profesores_seleccionados
        ]

    try:

        grupo = None

        print("\n🧠 EJECUTANDO ALGORITMO")
        print("Entradas usadas:", len(entradas))

        resultado = find_best_meeting_slot(entradas, grupo=None)

        print("RESULTADO:", resultado)

        session["resultado"] = resultado

        return redirect(url_for("resultado"))

    except Exception as exc:

        logger.exception("Error algoritmo")

        flash(f"Error durante el cálculo: {exc}", "danger")

        return redirect(url_for("generar"))


# -----------------------------------------------------------------------------
# Resultado
# -----------------------------------------------------------------------------

@app.route("/resultado")
@requiere_horario
def resultado():

    res = session.get("resultado")

    if not res:

        return redirect(url_for("generar"))

    slot_texto = "-"

    if res.get("slot_optimo"):

        dia, hora = res["slot_optimo"]

        dia_nombre = NOMBRES_DIAS.get(dia, f"Día {dia}")

        slot_texto = f"{dia_nombre} - Sesión {hora}"

    return render_template(
        "resultado.html",
        slot_texto=slot_texto
    )


# -----------------------------------------------------------------------------
# Limpiar sesión
# -----------------------------------------------------------------------------

@app.route("/limpiar", methods=["POST"])
def limpiar():

    session.clear()

    flash("Sesión limpiada.", "info")

    return redirect(url_for("index"))


# -----------------------------------------------------------------------------
# Run server
# -----------------------------------------------------------------------------

if __name__ == "__main__":

    app.run(debug=True, host="0.0.0.0", port=5000)