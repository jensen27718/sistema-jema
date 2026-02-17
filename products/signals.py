"""
Signals de productos para mantener variantes sincronizadas.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from products.models import Color, Product
from products.services import sincronizar_color_en_productos, sincronizar_variantes_producto


SUPPORTED_PRODUCT_TYPES = {"vinilo_corte", "cinta", "impreso_globo"}


@receiver(post_save, sender=Product)
def sync_variants_for_product(sender, instance, created, raw=False, **kwargs):
    """
    Crea variantes faltantes automaticamente cuando se crea/actualiza un producto.
    """
    if raw:
        return
    if not instance.is_active:
        return
    if instance.product_type not in SUPPORTED_PRODUCT_TYPES:
        return

    sincronizar_variantes_producto(instance)


@receiver(post_save, sender=Color)
def sync_color_for_existing_products(sender, instance, created, raw=False, **kwargs):
    """
    Cuando se crea un color nuevo de venta, lo propaga a productos activos.
    """
    if raw or not created:
        return
    if (instance.name or "").strip().lower() == "full color":
        return

    sincronizar_color_en_productos(instance, only_active=True)
