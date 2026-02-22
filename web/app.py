import sys
import os
from flask import Flask, render_template

# Esto le dice a Python que busque módulos en la carpeta principal del proyecto
# Así podemos importar desde la carpeta 'src' sin que dé error
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.logica_horarios import horarios_bp

app = Flask(__name__)

app.register_blueprint(horarios_bp)

@app.route('/')
def inicio():
    return render_template('index.html')

@app.route('/subir-pdf')
def subir_pdf():
    return render_template('subir_pdf.html')

@app.route('/generar-horario')
def generar_horario():
    return render_template('generar_horario.html')

if __name__ == '__main__':
    app.run(debug=True)