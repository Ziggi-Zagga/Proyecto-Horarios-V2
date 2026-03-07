import pdfplumber
import re


def parsear_pdf_profesor(ruta_pdf):

    entradas = []
    profesor = "DESCONOCIDO"

    with pdfplumber.open(ruta_pdf) as pdf:

        pagina = pdf.pages[0]

        texto = pagina.extract_text()

        # detectar profesor
        if texto:
            match = re.search(r"PROFESOR\s*(\d+)", texto, re.IGNORECASE)
            if match:
                profesor = match.group(1)

        tablas = pagina.extract_tables()

        for tabla in tablas:

            if not tabla:
                continue

            for fila in tabla[1:]:

                if not fila:
                    continue

                hora_texto = fila[0]

                if not hora_texto:
                    continue

                # convertir hora a número de sesión
                try:
                    hora = int(hora_texto.split(":")[0])
                except:
                    continue

                for col in range(1, 6):

                    celda = fila[col]

                    if not celda:
                        continue

                    texto = celda.upper()

                    if "RECREO" in texto:
                        continue

                    entrada = {
                        "profesor_id": profesor,
                        "dia": col - 1,
                        "hora": hora,
                        "grupo": celda.strip(),
                    }

                    entradas.append(entrada)

    print("ENTRADAS DETECTADAS:", entradas)

    return entradas