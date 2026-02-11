"""Modelos para costos de pedidos."""
from django.db import models


class CostType(models.Model):
    """Tipos de costos disponibles para cargar gastos manuales."""

    UNIT_CHOICES = [
        ("unidad", "Por Unidad"),
        ("metro_lineal", "Metro Lineal"),
        ("metro_cuadrado", "Metro Cuadrado"),
        ("fijo", "Costo Fijo"),
    ]

    name = models.CharField("Nombre", max_length=100)
    unit = models.CharField("Unidad de medida", max_length=30, choices=UNIT_CHOICES, default="unidad")
    default_unit_price = models.DecimalField("Precio por defecto por unidad", max_digits=10, decimal_places=2, default=0)
    special_material_price = models.DecimalField(
        "Precio material especial (Metalizado)",
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Precio para materiales marcados como especiales (ej: Metalizado, Mailan)",
    )
    accounting_category = models.ForeignKey(
        "contabilidad.TransactionCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cost_types",
        limit_choices_to={"transaction_type": "egreso"},
        verbose_name="Categoria contable por defecto",
    )
    description = models.TextField("Descripción", blank=True)
    is_active = models.BooleanField("Activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tipo de Costo"
        verbose_name_plural = "Tipos de Costo"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_unit_display()})"


class ProductTypeCostConfig(models.Model):
    """
    Legacy model from the automatic cost engine.
    Kept for DB compatibility, no longer used by the active flow.
    """

    CALC_METHOD_CHOICES = [
        ("per_unit", "Por unidad (cantidad × precio)"),
        ("linear_meters", "Metros lineales (layout en material)"),
        ("square_meters", "Metros cuadrados (alto × ancho)"),
        ("manual", "Manual (ingresado por admin)"),
    ]

    product_type = models.CharField("Tipo de producto", max_length=50)
    cost_type = models.ForeignKey(CostType, on_delete=models.CASCADE, verbose_name="Tipo de costo")
    calculation_method = models.CharField("Método de cálculo", max_length=30, choices=CALC_METHOD_CHOICES, default="per_unit")
    material_width_cm = models.DecimalField(
        "Ancho del material (cm)",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Ancho del rollo/material para cálculos de metros lineales",
    )
    position = models.IntegerField("Orden de display", default=0)

    class Meta:
        verbose_name = "Config. Costo por Tipo de Producto"
        verbose_name_plural = "Config. Costos por Tipo de Producto"
        unique_together = ("product_type", "cost_type")
        ordering = ["product_type", "position"]

    def __str__(self):
        return f"{self.get_product_type_display()} -> {self.cost_type.name}"

    def get_product_type_display(self):
        from products.models import Product

        type_dict = dict(Product.TYPE_CHOICES)
        return type_dict.get(self.product_type, self.product_type)


class OrderCostBreakdown(models.Model):
    """Gastos registrados manualmente en pedidos."""

    ACCOUNTING_STATUS_PENDING = "pending"
    ACCOUNTING_STATUS_POSTED = "posted"
    ACCOUNTING_STATUS_CHOICES = [
        (ACCOUNTING_STATUS_PENDING, "Pendiente"),
        (ACCOUNTING_STATUS_POSTED, "Registrado en contabilidad"),
    ]

    order = models.ForeignKey(
        "products.Order",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cost_breakdowns",
    )
    internal_order = models.ForeignKey(
        "products.InternalOrder",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cost_breakdowns",
    )
    cost_type = models.ForeignKey(CostType, on_delete=models.PROTECT, verbose_name="Tipo de costo")
    product_type = models.CharField("Tipo de producto", max_length=50, blank=True)
    description = models.CharField("Descripción", max_length=255)
    calculated_quantity = models.DecimalField("Cantidad calculada", max_digits=10, decimal_places=4, default=0)
    unit_price = models.DecimalField("Precio unitario", max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField("Total", max_digits=12, decimal_places=2, default=0)
    is_manual = models.BooleanField("Ingresado manualmente", default=False)
    is_system_generated = models.BooleanField("Generado automáticamente", default=False, help_text="Indica si fue creado automáticamente (descuento/envío)")
    
    COST_CATEGORY_CHOICES = [
        ('production', 'Producción'),
        ('discount', 'Descuento'),
        ('shipping', 'Envío'),
        ('other', 'Otro'),
    ]
    cost_category = models.CharField("Categoría de costo", max_length=20, choices=COST_CATEGORY_CHOICES, default='production')
    notes = models.TextField("Notas", blank=True)

    accounting_category = models.ForeignKey(
        "contabilidad.TransactionCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_cost_breakdowns",
        limit_choices_to={"transaction_type": "egreso"},
        verbose_name="Categoria contable",
    )
    accounting_status = models.CharField(
        "Estado contable",
        max_length=20,
        choices=ACCOUNTING_STATUS_CHOICES,
        default=ACCOUNTING_STATUS_PENDING,
    )
    accounting_transaction = models.OneToOneField(
        "contabilidad.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_cost_breakdown",
        verbose_name="Movimiento contable",
    )
    accounting_posted_at = models.DateTimeField("Fecha de registro contable", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Desglose de Costo"
        verbose_name_plural = "Desgloses de Costos"
        ordering = ["product_type", "cost_type__name"]

    def __str__(self):
        return f"{self.description} - ${self.total}"
