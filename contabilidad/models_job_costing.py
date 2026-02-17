"""
Modelos para Job Costing — Costeo por Pedido, Overhead y Distribución de Utilidades
"""
from django.db import models
from django.conf import settings


class JobCostingConfig(models.Model):
    """Configuración singleton (pk=1) para parámetros de distribución"""
    savings_percentage = models.DecimalField(
        "% Ahorro Empresa", max_digits=5, decimal_places=2, default=5.00
    )
    distribution_percentage = models.DecimalField(
        "% Distribución Socios", max_digits=5, decimal_places=2, default=95.00
    )
    cuenta_principal = models.ForeignKey(
        'contabilidad.Account', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name="Cuenta Principal (Ingresos)"
    )
    cuenta_costos = models.ForeignKey(
        'contabilidad.Account', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name="Cuenta Reserva Costos"
    )
    cuenta_ahorro = models.ForeignKey(
        'contabilidad.Account', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name="Cuenta Ahorro Empresa"
    )
    cuenta_distribucion = models.ForeignKey(
        'contabilidad.Account', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name="Cuenta Distribución Socios"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración Job Costing"
        verbose_name_plural = "Configuración Job Costing"

    def __str__(self):
        return f"Config Job Costing (Ahorro {self.savings_percentage}% / Distrib. {self.distribution_percentage}%)"

    @classmethod
    def get_config(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Partner(models.Model):
    """Socio del negocio que recibe distribución de utilidades"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='partner_profile',
        verbose_name="Usuario vinculado"
    )
    name = models.CharField("Nombre", max_length=200)
    share_percentage = models.DecimalField(
        "% del Distributable", max_digits=5, decimal_places=2, default=0,
        help_text="Porcentaje del monto distribuible (95%) que le corresponde"
    )
    is_active = models.BooleanField("Activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Socio"
        verbose_name_plural = "Socios"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.share_percentage}%)"


class FinancialStatus(models.Model):
    """Estado financiero de un pedido, separado del estado operativo"""
    STATE_CHOICES = [
        ('creado', 'Creado'),
        ('material_comprado', 'Material Comprado'),
        ('en_produccion', 'En Produccion'),
        ('entregado', 'Entregado'),
        ('enviado', 'Enviado (Legacy)'),
        ('cobrado', 'Cobrado'),
        ('cancelado', 'Cancelado'),
    ]

    order = models.OneToOneField(
        'products.Order', on_delete=models.CASCADE,
        null=True, blank=True, related_name='financial_status'
    )
    internal_order = models.OneToOneField(
        'products.InternalOrder', on_delete=models.CASCADE,
        null=True, blank=True, related_name='financial_status'
    )
    state = models.CharField("Estado Financiero", max_length=20, choices=STATE_CHOICES, default='creado')
    sale_amount = models.DecimalField("Monto de Venta", max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField("Fecha de Envío", null=True, blank=True)
    collected_at = models.DateTimeField("Fecha de Cobro", null=True, blank=True)
    cancelled_at = models.DateTimeField("Fecha de Cancelación", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+'
    )
    notes = models.TextField("Notas", blank=True)

    class Meta:
        verbose_name = "Estado Financiero"
        verbose_name_plural = "Estados Financieros"
        ordering = ['-created_at']

    def __str__(self):
        if self.order:
            return f"Pedido #{self.order.id} — {self.get_state_display()}"
        elif self.internal_order:
            return f"Pedido Interno #{self.internal_order.id} — {self.get_state_display()}"
        return f"FinancialStatus #{self.pk}"

    @property
    def order_ref(self):
        if self.order:
            return f"PED-{self.order.id}"
        elif self.internal_order:
            return f"INT-{self.internal_order.id}"
        return "—"

    @property
    def order_type(self):
        if self.order:
            return 'catalog'
        elif self.internal_order:
            return 'internal'
        return None

    def get_state_badge_class(self):
        return {
            'creado': 'bg-secondary',
            'material_comprado': 'bg-info',
            'en_produccion': 'bg-warning text-dark',
            'entregado': 'bg-primary',
            'enviado': 'bg-primary',
            'cobrado': 'bg-success',
            'cancelado': 'bg-danger',
        }.get(self.state, 'bg-secondary')


class FinancialWeek(models.Model):
    """Período semanal financiero (Lunes-Domingo)"""
    STATUS_CHOICES = [
        ('open', 'Abierta'),
        ('closed', 'Cerrada'),
    ]

    year = models.PositiveIntegerField("Año")
    week_number = models.PositiveIntegerField("Semana")
    start_date = models.DateField("Fecha Inicio (Lunes)")
    end_date = models.DateField("Fecha Fin (Domingo)")
    status = models.CharField("Estado", max_length=10, choices=STATUS_CHOICES, default='open')

    # Snapshot — se llenan al cerrar la semana
    total_sales = models.DecimalField("Ventas Totales", max_digits=12, decimal_places=2, default=0)
    total_direct_costs = models.DecimalField("Costos Directos", max_digits=12, decimal_places=2, default=0)
    total_fixed_costs = models.DecimalField("Gastos Fijos", max_digits=12, decimal_places=2, default=0)
    overhead_percentage = models.DecimalField("% Overhead", max_digits=7, decimal_places=4, default=0)
    total_overhead_applied = models.DecimalField("Overhead Aplicado", max_digits=12, decimal_places=2, default=0)
    total_net_profit = models.DecimalField("Utilidad Neta", max_digits=12, decimal_places=2, default=0)
    savings_amount = models.DecimalField("Monto Ahorro", max_digits=12, decimal_places=2, default=0)
    distributable_amount = models.DecimalField("Monto Distribuible", max_digits=12, decimal_places=2, default=0)
    orders_count = models.PositiveIntegerField("Pedidos Cobrados", default=0)

    closed_at = models.DateTimeField("Cerrada en", null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+'
    )
    notes = models.TextField("Notas", blank=True)

    class Meta:
        verbose_name = "Semana Financiera"
        verbose_name_plural = "Semanas Financieras"
        unique_together = ('year', 'week_number')
        ordering = ['-year', '-week_number']

    def __str__(self):
        return f"Semana {self.week_number}/{self.year} ({self.start_date} — {self.end_date})"


class OrderFinancialSnapshot(models.Model):
    """Rentabilidad calculada por pedido al cerrar la semana"""
    financial_week = models.ForeignKey(
        FinancialWeek, on_delete=models.CASCADE, related_name='order_snapshots'
    )
    financial_status = models.OneToOneField(
        FinancialStatus, on_delete=models.CASCADE, related_name='financial_snapshot'
    )
    sale_amount = models.DecimalField("Venta", max_digits=12, decimal_places=2)
    direct_costs = models.DecimalField("Costos Directos", max_digits=12, decimal_places=2)
    shipping_cost = models.DecimalField("Envío", max_digits=12, decimal_places=2, default=0)
    overhead_percentage = models.DecimalField("% Overhead", max_digits=7, decimal_places=4)
    overhead_amount = models.DecimalField("Monto Overhead", max_digits=12, decimal_places=2)
    net_profit = models.DecimalField("Utilidad Neta", max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Snapshot Financiero de Pedido"
        verbose_name_plural = "Snapshots Financieros de Pedidos"

    def __str__(self):
        return f"{self.financial_status.order_ref} — Utilidad ${self.net_profit}"


class PartnerDistribution(models.Model):
    """Distribución de utilidad a un socio en una semana"""
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('paid', 'Pagado'),
    ]

    financial_week = models.ForeignKey(
        FinancialWeek, on_delete=models.CASCADE, related_name='distributions'
    )
    partner = models.ForeignKey(
        Partner, on_delete=models.CASCADE, related_name='distributions'
    )
    share_percentage = models.DecimalField("% Asignado", max_digits=5, decimal_places=2)
    gross_amount = models.DecimalField("Monto Bruto", max_digits=12, decimal_places=2)
    status = models.CharField("Estado", max_length=10, choices=STATUS_CHOICES, default='pending')
    transaction = models.ForeignKey(
        'contabilidad.Transaction', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+'
    )
    paid_at = models.DateTimeField("Pagado en", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Distribución a Socio"
        verbose_name_plural = "Distribuciones a Socios"
        unique_together = ('financial_week', 'partner')

    def __str__(self):
        return f"{self.partner.name} — Sem {self.financial_week.week_number}/{self.financial_week.year} — ${self.gross_amount}"
