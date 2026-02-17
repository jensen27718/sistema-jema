"""
Funciones de procesamiento para carga masiva de productos.
TODO SÍNCRONO - Sin Celery para compatibilidad con PythonAnywhere.
"""
import logging
import os
from django.utils import timezone
from .models import Product
from .ai_services import (
    extract_product_name_from_file
)
from .services import sincronizar_variantes_producto

logger = logging.getLogger(__name__)


def process_single_upload_item(item, product_type):
    """
    Procesa un archivo individual del lote.
    COPIADO DE LA LÓGICA DE CARGA INDIVIDUAL QUE SÍ FUNCIONA.

    Args:
        item: BulkUploadItem a procesar
        product_type: Tipo de producto seleccionado por el usuario
    """
    # 1. Extraer nombre del producto desde nombre de archivo
    product_name = extract_product_name_from_file(item.original_filename)
    logger.info("Bulk procesando: %s como %s", product_name, product_type)

    # 2. Descripción en blanco (como solicitó el usuario)
    ai_description = ""

    # Guardar descripción (vacía)
    item.ai_extracted_description = ai_description
    item.save()

    # 3. Crear producto EXACTAMENTE como en la carga individual
    # Django maneja automáticamente source_file y genera la imagen en Product.save()
    # Aseguramos que el puntero esté al inicio antes de pasar el archivo
    item.source_file.seek(0)
    
    product = Product.objects.create(
        name=product_name,
        product_type=product_type,  # Usar el tipo seleccionado por el usuario
        description=ai_description,
        source_file=item.source_file,  # Django lo copia automáticamente
        is_online=False  # Offline por defecto para revisión
    )
    
    # Ahora sí podemos cerrar el archivo fuente del item masivo
    try:
        item.source_file.close()
    except:
        pass

    logger.info("Bulk producto creado: #%d - %s", product.id, product.name)

    # 4. Generar variantes segun tipo
    count = sincronizar_variantes_producto(product)

    logger.info("Bulk %d variantes generadas para %s", count, product.name)

    # 5. Vincular item con producto
    item.product = product
    item.status = 'completed'
    item.processed_at = timezone.now()
    item.save()
