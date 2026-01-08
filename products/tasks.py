"""
Funciones de procesamiento para carga masiva de productos.
TODO SÍNCRONO - Sin Celery para compatibilidad con PythonAnywhere.
"""
from django.utils import timezone
from .models import Product
from .ai_services import (
    extract_product_name_from_file
)
from .services import generar_variantes_vinilo, generar_variantes_impresos
import os


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
    print(f"[Bulk] Procesando: {product_name} como {product_type}")

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

    print(f"[Bulk] Producto creado: #{product.id} - {product.name}")
    print(f"[Bulk] Imagen generada: {product.image.name if product.image else 'NO GENERADA'}")

    # 4. Generar variantes según tipo
    if product_type == 'vinilo_corte':
        count = generar_variantes_vinilo(product)
    elif product_type == 'impreso_globo':
        count = generar_variantes_impresos(product)
    else:
        count = 0

    print(f"[Bulk] {count} variantes generadas")

    # 5. Vincular item con producto
    item.product = product
    item.status = 'completed'
    item.processed_at = timezone.now()
    item.save()

    print(f"[Bulk] Completado: {product.name}")
