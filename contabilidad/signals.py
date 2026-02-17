"""
Signals para auto-crear FinancialStatus cuando se crean pedidos
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='products.Order')
def create_financial_status_for_order(sender, instance, created, **kwargs):
    """Mantiene sincronizado FinancialStatus para pedidos catalogo."""
    from contabilidad.job_costing_services import ensure_financial_status
    ensure_financial_status(order=instance)


@receiver(post_save, sender='products.InternalOrder')
def create_financial_status_for_internal_order(sender, instance, created, **kwargs):
    """Mantiene sincronizado FinancialStatus para pedidos internos."""
    from contabilidad.job_costing_services import ensure_financial_status
    ensure_financial_status(internal_order=instance)
