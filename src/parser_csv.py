# =============================================================================
# parser_csv.py
# -----------------------------------------------------------------------------
# Parses uploaded schedule files (CSV or JSON) into a list of raw entry dicts.
#
# Responsibilities:
#   • Detect file type from extension / content.
#   • Parse CSV files via the csv standard library.
#   • Parse JSON files via the json standard library.
#   • Return a uniform list[dict] — the same structure expected by
#     horarios.normalizar_entradas().
#   • Raise clear, user-friendly errors on malformed input.
#
# This module does NOT validate field values — that is horarios.py's job.
# =============================================================================

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ParseError(ValueError):
    """Raised when the uploaded file cannot be parsed."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parsear_archivo(contenido: bytes, nombre_archivo: str) -> list[dict[str, Any]]:
    """
    Parse an uploaded file into a list of raw schedule entry dicts.

    Supports:
      • ``.json`` — array of objects
      • ``.csv``  — header row + data rows

    Parameters
    ----------
    contenido       : bytes   — raw file bytes from the upload
    nombre_archivo  : str     — original filename (used to detect format)

    Returns
    -------
    list[dict]
        Raw entries.  Fields are returned as-is (strings from CSV, native
        types from JSON).  Type coercion happens in ``horarios.normalizar_entradas``.

    Raises
    ------
    ParseError
        On any parsing failure with a descriptive message.
    """
    extension = _detectar_extension(nombre_archivo)

    if extension == "json":
        return _parsear_json(contenido, nombre_archivo)
    elif extension == "csv":
        return _parsear_csv(contenido, nombre_archivo)
    else:
        raise ParseError(
            f"Formato no soportado: '{extension}'. "
            "Por favor, sube un archivo .json o .csv."
        )


def parsear_ejemplo() -> list[dict[str, Any]]:
    """
    Return a built-in example dataset for demonstration purposes.

    The dataset includes three groups with overlapping teachers to make
    the optimisation problem interesting.

    Returns
    -------
    list[dict]
    """
    return _EJEMPLO_DATASET


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detectar_extension(nombre_archivo: str) -> str:
    """Return the lowercase file extension (without dot), or '' if absent."""
    partes = nombre_archivo.rsplit(".", 1)
    if len(partes) == 2:
        return partes[1].strip().lower()
    return ""


def _parsear_json(contenido: bytes, nombre: str) -> list[dict[str, Any]]:
    """Parse JSON bytes → list[dict]."""
    try:
        texto = contenido.decode("utf-8", errors="replace")
    except Exception as exc:
        raise ParseError(f"No se pudo leer '{nombre}' como texto UTF-8: {exc}") from exc

    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ParseError(
            f"Error de sintaxis JSON en '{nombre}': {exc.msg} "
            f"(línea {exc.lineno}, columna {exc.colno})."
        ) from exc

    if not isinstance(datos, list):
        raise ParseError(
            f"'{nombre}' debe contener un array JSON de objetos, "
            f"no {type(datos).__name__}."
        )

    if not datos:
        raise ParseError(f"'{nombre}' está vacío — no se encontraron entradas.")

    # Validate each item is a dict
    for i, item in enumerate(datos):
        if not isinstance(item, dict):
            raise ParseError(
                f"'{nombre}': el elemento #{i} no es un objeto JSON "
                f"(recibido {type(item).__name__})."
            )

    logger.info("JSON parseado: %d entradas desde '%s'.", len(datos), nombre)
    return datos


def _parsear_csv(contenido: bytes, nombre: str) -> list[dict[str, Any]]:
    """Parse CSV bytes → list[dict] using the first row as header."""
    try:
        texto = contenido.decode("utf-8-sig", errors="replace")  # handle BOM
    except Exception as exc:
        raise ParseError(f"No se pudo leer '{nombre}' como texto UTF-8: {exc}") from exc

    # Auto-detect delimiter (comma or semicolon)
    delimitador = _detectar_delimitador(texto)

    reader = csv.DictReader(io.StringIO(texto), delimiter=delimitador)

    try:
        filas = list(reader)
    except csv.Error as exc:
        raise ParseError(f"Error al parsear CSV '{nombre}': {exc}") from exc

    if reader.fieldnames is None or len(reader.fieldnames) == 0:
        raise ParseError(f"'{nombre}': no se encontró cabecera CSV.")

    if not filas:
        raise ParseError(f"'{nombre}' está vacío — no se encontraron filas de datos.")

    # Normalise field names: strip spaces, lowercase
    entradas = []
    for i, fila in enumerate(filas):
        # csv.DictReader may include None key for extra columns — discard it
        entrada = {
            k.strip().lower(): v.strip() if isinstance(v, str) else v
            for k, v in fila.items()
            if k is not None
        }
        entradas.append(entrada)

    logger.info("CSV parseado: %d filas desde '%s' (delimitador=%r).", len(entradas), nombre, delimitador)
    return entradas


def _detectar_delimitador(texto: str) -> str:
    """
    Heuristically detect the CSV delimiter.
    Checks the first non-empty line for comma vs semicolon count.
    Defaults to comma.
    """
    primera_linea = ""
    for linea in texto.splitlines():
        if linea.strip():
            primera_linea = linea
            break

    n_coma       = primera_linea.count(",")
    n_punto_coma = primera_linea.count(";")

    return ";" if n_punto_coma > n_coma else ","


# ---------------------------------------------------------------------------
# Built-in example dataset
# ---------------------------------------------------------------------------

_EJEMPLO_DATASET: list[dict[str, Any]] = [
    # ── 2ESO-A ── taught by P1, P2, P3, P4
    {"profesor_id": "P1", "dia": 0, "hora": 1, "grupo": "2ESO-A", "tarea": "Matemáticas"},
    {"profesor_id": "P1", "dia": 0, "hora": 2, "grupo": "2ESO-A", "tarea": "Matemáticas"},
    {"profesor_id": "P1", "dia": 1, "hora": 3, "grupo": "2ESO-A", "tarea": "Matemáticas"},
    {"profesor_id": "P1", "dia": 2, "hora": 1, "grupo": "2ESO-A", "tarea": "Matemáticas"},
    {"profesor_id": "P1", "dia": 3, "hora": 5, "grupo": "2ESO-A", "tarea": "Matemáticas"},
    {"profesor_id": "P1", "dia": 4, "hora": 2, "grupo": "2ESO-A", "tarea": "Matemáticas"},

    {"profesor_id": "P2", "dia": 0, "hora": 3, "grupo": "2ESO-A", "tarea": "Lengua"},
    {"profesor_id": "P2", "dia": 1, "hora": 1, "grupo": "2ESO-A", "tarea": "Lengua"},
    {"profesor_id": "P2", "dia": 2, "hora": 5, "grupo": "2ESO-A", "tarea": "Lengua"},
    {"profesor_id": "P2", "dia": 3, "hora": 2, "grupo": "2ESO-A", "tarea": "Lengua"},
    {"profesor_id": "P2", "dia": 4, "hora": 6, "grupo": "2ESO-A", "tarea": "Lengua"},

    {"profesor_id": "P3", "dia": 0, "hora": 5, "grupo": "2ESO-A", "tarea": "Inglés"},
    {"profesor_id": "P3", "dia": 1, "hora": 6, "grupo": "2ESO-A", "tarea": "Inglés"},
    {"profesor_id": "P3", "dia": 2, "hora": 2, "grupo": "2ESO-A", "tarea": "Inglés"},
    {"profesor_id": "P3", "dia": 3, "hora": 1, "grupo": "2ESO-A", "tarea": "Inglés"},
    {"profesor_id": "P3", "dia": 4, "hora": 3, "grupo": "2ESO-A", "tarea": "Inglés"},

    {"profesor_id": "P4", "dia": 0, "hora": 6, "grupo": "2ESO-A", "tarea": "CCNN"},
    {"profesor_id": "P4", "dia": 1, "hora": 2, "grupo": "2ESO-A", "tarea": "CCNN"},
    {"profesor_id": "P4", "dia": 2, "hora": 6, "grupo": "2ESO-A", "tarea": "CCNN"},
    {"profesor_id": "P4", "dia": 3, "hora": 3, "grupo": "2ESO-A", "tarea": "CCNN"},
    {"profesor_id": "P4", "dia": 4, "hora": 1, "grupo": "2ESO-A", "tarea": "CCNN"},

    # ── 1BACH-B ── taught by P1, P5, P6
    {"profesor_id": "P1", "dia": 0, "hora": 5, "grupo": "1BACH-B", "tarea": "Matemáticas"},
    {"profesor_id": "P1", "dia": 1, "hora": 1, "grupo": "1BACH-B", "tarea": "Matemáticas"},
    {"profesor_id": "P1", "dia": 2, "hora": 3, "grupo": "1BACH-B", "tarea": "Matemáticas"},

    {"profesor_id": "P5", "dia": 0, "hora": 2, "grupo": "1BACH-B", "tarea": "Historia"},
    {"profesor_id": "P5", "dia": 2, "hora": 5, "grupo": "1BACH-B", "tarea": "Historia"},
    {"profesor_id": "P5", "dia": 4, "hora": 2, "grupo": "1BACH-B", "tarea": "Historia"},

    {"profesor_id": "P6", "dia": 1, "hora": 5, "grupo": "1BACH-B", "tarea": "Filosofía"},
    {"profesor_id": "P6", "dia": 3, "hora": 2, "grupo": "1BACH-B", "tarea": "Filosofía"},
    {"profesor_id": "P6", "dia": 4, "hora": 6, "grupo": "1BACH-B", "tarea": "Filosofía"},

    # ── 3FP-DIGI ── taught by P7, P8
    {"profesor_id": "P7", "dia": 0, "hora": 1, "grupo": "3FP-DIGI", "tarea": "Programación"},
    {"profesor_id": "P7", "dia": 0, "hora": 2, "grupo": "3FP-DIGI", "tarea": "Programación"},
    {"profesor_id": "P7", "dia": 0, "hora": 3, "grupo": "3FP-DIGI", "tarea": "Programación"},
    {"profesor_id": "P7", "dia": 1, "hora": 1, "grupo": "3FP-DIGI", "tarea": "Programación"},
    {"profesor_id": "P7", "dia": 1, "hora": 2, "grupo": "3FP-DIGI", "tarea": "Programación"},
    {"profesor_id": "P7", "dia": 1, "hora": 3, "grupo": "3FP-DIGI", "tarea": "Programación"},
    {"profesor_id": "P7", "dia": 2, "hora": 1, "grupo": "3FP-DIGI", "tarea": "Programación"},
    {"profesor_id": "P7", "dia": 2, "hora": 2, "grupo": "3FP-DIGI", "tarea": "Programación"},
    {"profesor_id": "P7", "dia": 3, "hora": 1, "grupo": "3FP-DIGI", "tarea": "Programación"},
    {"profesor_id": "P7", "dia": 3, "hora": 2, "grupo": "3FP-DIGI", "tarea": "Programación"},
    {"profesor_id": "P7", "dia": 4, "hora": 1, "grupo": "3FP-DIGI", "tarea": "Programación"},
    {"profesor_id": "P7", "dia": 4, "hora": 2, "grupo": "3FP-DIGI", "tarea": "Programación"},

    {"profesor_id": "P8", "dia": 0, "hora": 5, "grupo": "3FP-DIGI", "tarea": "Redes"},
    {"profesor_id": "P8", "dia": 0, "hora": 6, "grupo": "3FP-DIGI", "tarea": "Redes"},
    {"profesor_id": "P8", "dia": 1, "hora": 5, "grupo": "3FP-DIGI", "tarea": "Redes"},
    {"profesor_id": "P8", "dia": 1, "hora": 6, "grupo": "3FP-DIGI", "tarea": "Redes"},
    {"profesor_id": "P8", "dia": 2, "hora": 5, "grupo": "3FP-DIGI", "tarea": "Redes"},
    {"profesor_id": "P8", "dia": 2, "hora": 6, "grupo": "3FP-DIGI", "tarea": "Redes"},
    {"profesor_id": "P8", "dia": 3, "hora": 5, "grupo": "3FP-DIGI", "tarea": "Redes"},
    {"profesor_id": "P8", "dia": 3, "hora": 6, "grupo": "3FP-DIGI", "tarea": "Redes"},
    {"profesor_id": "P8", "dia": 4, "hora": 5, "grupo": "3FP-DIGI", "tarea": "Redes"},
    {"profesor_id": "P8", "dia": 4, "hora": 6, "grupo": "3FP-DIGI", "tarea": "Redes"},
]
