import sys
import os
from flask import Flask, render_template

# Esto le dice a Python que busque módulos en la carpeta principal del proyecto
# Así podemos importar desde la carpeta 'src' sin que dé error
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.logica_horarios import horarios_bp
from src.subir_pdfs import subir_pdfs_bp

app = Flask(__name__)

app.register_blueprint(horarios_bp)
app.register_blueprint(subir_pdfs_bp)

@app.route('/')
def inicio():
    return render_template('index.html')

@app.route('/subir-pdf')
def subir_pdf():
    return render_template('subir_pdf.html')

@app.route('/generar-horario')
def generar_horario():
    from src.subir_pdfs import datos_profesores
    from src.logica_horarios import grupos_por_nivel, NIVEL_LABELS

    return render_template(
        'generar_horario.html',
        grupos_por_nivel=grupos_por_nivel(datos_profesores),
        nivel_labels=NIVEL_LABELS,
        hay_datos=bool(datos_profesores),
    )

@app.route('/profesores')
def profesores():
    return render_template('profesores.html')

if __name__ == '__main__':
    app.run(debug=True)