"""
Servicios de IA - ELIMINADO por solicitud del usuario.
Se mantienen funciones vacías para evitar errores de importación.
"""
import os
import re

def extract_content_from_pdf(pdf_file):
    return ""

def extract_content_from_image(image_file):
    return ""

def extract_product_name_from_file(filename):
    """
    Limpia el nombre de archivo para crear un nombre de producto legible.
    CONSERVADO: Es útil para el catálogo aunque no use IA.
    """
    # Remover extensión
    name = os.path.splitext(filename)[0]

    # Remover prefijos comunes SOLO si queda algo después
    new_name = re.sub(r'^(sticker|vinilo|product|impreso|logo)[-_]', '', name, flags=re.IGNORECASE)
    if new_name.strip():
        name = new_name

    # Remover números y guiones al inicio SOLO si queda algo después
    new_name = re.sub(r'^[\d_-]+', '', name)
    if new_name.strip():
        name = new_name

    # Reemplazar guiones bajos y guiones por espacios
    name = name.replace('_', ' ').replace('-', ' ')

    # Remover espacios múltiples
    name = re.sub(r'\s+', ' ', name)

    # Capitalizar palabras
    name = name.strip().title()

    if not name:
        name = "Producto Sin Nombre"

    return name

def test_gemini_connection():
    return {"success": False, "message": "IA Deshabilitada"}
