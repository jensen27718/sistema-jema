"""
Modelos para el sistema de Pedidos Internos con Drag & Drop
"""
from decimal import Decimal
from django.db import models
from django.conf import settings


class InternalOrder(models.Model):
    """Pedido interno creado desde el dashboard"""
    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('confirmed', 'Confirmado'),
        ('in_production', 'En Producción'),
        ('completed', 'Completado'),
        ('cancelled', 'Cancelado'),
    ]

    name = models.CharField("Nombre del pedido", max_length=200)
    description = models.TextField("Descripción", blank=True)
    status = models.CharField("Estado", max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Creado por"
    )
    created_at = models.DateTimeField("Fecha de creación", auto_now_add=True)
    updated_at = models.DateTimeField("Última actualización", auto_now=True)

    # Campos calculados
    total_items = models.IntegerField("Total de items", default=0)
    total_estimated = models.DecimalField(
        "Total estimado",
        max_digits=12,
        decimal_places=2,
        default=0
    )
    shipping_cost = models.DecimalField(
        "Costo de envío",
        max_digits=10,
        decimal_places=2,
        default=0
    )
    discount_amount = models.DecimalField(
        "Descuento especial",
        max_digits=12,
        decimal_places=2,
        default=0
    )
    discount_percentage = models.DecimalField(
        "Porcentaje de descuento",
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Porcentaje de descuento sobre el total (0-100)"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Pedido Interno"
        verbose_name_plural = "Pedidos Internos"

    def __str__(self):
        return f"#{self.id} - {self.name}"

    def get_status_color(self):
        """Retorna el color CSS para el estado"""
        colors = {
            'draft': 'secondary',
            'confirmed': 'primary',
            'in_production': 'warning',
            'completed': 'success',
            'cancelled': 'danger',
        }
        return colors.get(self.status, 'secondary')

    @property
    def items_breakdown(self):
        """Retorna un desglose de cantidades por tipo de producto"""
        from django.db.models import Sum
        from products.models import Product
        
        breakdown = self.items.values('variant__product__product_type').annotate(total_qty=Sum('quantity'))
        type_map = dict(Product.TYPE_CHOICES)
        
        result = []
        for entry in breakdown:
            p_type = entry['variant__product__product_type']
            if p_type:
                label = type_map.get(p_type, p_type.replace('_', ' ').title())
                result.append({
                    'label': label,
                    'total': entry['total_qty']
                })
        return result

    @property
    def total_items_price(self):
        """Suma de cantidad * precio de todos los items"""
        from django.db.models import Sum, F
        return self.items.aggregate(
            total=Sum(F('quantity') * F('unit_price'))
        )['total'] or 0

    def recalculate_totals(self):
        """Recalcula los totales del pedido"""
        from django.db.models import Sum, F

        aggregates = self.items.aggregate(
            total_qty=Sum('quantity'),
            total_price=Sum(F('quantity') * F('unit_price'))
        )

        # Sumar también los gastos manuales cargados al pedido
        expenses_total = self.cost_breakdowns.aggregate(total=Sum('total'))['total'] or 0

        self.total_items = aggregates['total_qty'] or 0
        total_price = aggregates['total_price'] or 0
        
        self.total_estimated = total_price - (self.discount_amount or 0)
        self.save(update_fields=['total_items', 'total_estimated'])


class InternalOrderItem(models.Model):
    """Item individual de un pedido interno"""
    order = models.ForeignKey(
        InternalOrder,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Pedido"
    )
    variant = models.ForeignKey(
        'products.ProductVariant',
        on_delete=models.CASCADE,
        verbose_name="Variante"
    )
    quantity = models.PositiveIntegerField("Cantidad", default=1)
    completed_quantity = models.PositiveIntegerField("Cantidad completada", default=0)

    # Snapshot para histórico (se guarda al momento de agregar)
    product_name = models.CharField("Nombre del producto", max_length=200)
    variant_details = models.CharField("Detalles de variante", max_length=300)  # "Grande - Dorado - Vinilo"
    unit_price = models.DecimalField("Precio unitario", max_digits=10, decimal_places=2)

    created_at = models.DateTimeField("Fecha de agregado", auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = "Item de Pedido Interno"
        verbose_name_plural = "Items de Pedido Interno"

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"

    def get_subtotal(self):
        """Calcula el subtotal del item"""
        return self.quantity * self.unit_price

    def save(self, *args, **kwargs):
        # Auto-llenar campos snapshot si están vacíos
        if not self.product_name and self.variant:
            self.product_name = self.variant.product.name

        if not self.variant_details and self.variant:
            parts = []
            if self.variant.size:
                parts.append(self.variant.size.name)
            if self.variant.material:
                parts.append(self.variant.material.name)
            if self.variant.color:
                parts.append(self.variant.color.name)
            self.variant_details = " - ".join(parts) if parts else "Sin variante"

        if not self.unit_price and self.variant:
            self.unit_price = self.variant.price or 0

        super().save(*args, **kwargs)


class InternalOrderGroup(models.Model):
    """
    Agrupa items por tipo/categoría dentro de un pedido.
    Útil para organizar visualmente los pedidos grandes.
    """
    order = models.ForeignKey(
        InternalOrder,
        on_delete=models.CASCADE,
        related_name='groups',
        verbose_name="Pedido"
    )
    name = models.CharField("Nombre del grupo", max_length=100)  # "Vinilos Navidad", "Impresos Globo"
    product_type = models.CharField("Tipo de producto", max_length=50, blank=True)
    category = models.ForeignKey(
        'products.Category',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Categoría"
    )

    # Para ordenar grupos en la UI
    position = models.IntegerField("Posición", default=0)

    class Meta:
        ordering = ['position']
        verbose_name = "Grupo de Pedido"
        verbose_name_plural = "Grupos de Pedido"

    def __str__(self):
        return f"{self.name} - Pedido #{self.order_id}"
