from django.db import models
from django.conf import settings
from products.models import Order # Para vincular con pedidos (si se requiere)

class Account(models.Model):
    name = models.CharField("Nombre de la Cuenta", max_length=100) # Ej: Bancolombia, Efectivo, Nequi
    description = models.TextField("Descripción", blank=True)
    limit_amount = models.DecimalField("Límite Mensual", max_digits=12, decimal_places=2, default=0) # Tope visual
    
    # Campo acumulador simple (se actualizará con señales o guards)
    current_balance = models.DecimalField("Saldo Actual", max_digits=12, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} (${self.current_balance})"

class TransactionCategory(models.Model):
    TYPE_CHOICES = (
        ('ingreso', 'Ingreso'),
        ('egreso', 'Egreso/Gasto'),
    )
    name = models.CharField("Nombre de Categoría", max_length=100) # Ej: Ventas, Arriendo, Inventario
    transaction_type = models.CharField("Tipo", max_length=20, choices=TYPE_CHOICES)
    
    def __str__(self):
        return f"{self.name} ({self.get_transaction_type_display()})"

class Provider(models.Model):
    name = models.CharField("Nombre / Empresa", max_length=200)
    phone = models.CharField("Teléfono", max_length=50, blank=True)
    email = models.EmailField("Email", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Transaction(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transactions')
    category = models.ForeignKey(TransactionCategory, on_delete=models.PROTECT, null=True, blank=True) # Opcional para transferencias
    
    amount = models.DecimalField("Monto", max_digits=12, decimal_places=2)
    description = models.CharField("Descripción", max_length=255)
    
    # Vinculación con Cliente (Usuario del sistema)
    from users.models import User
    client = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    
    # Vinculación con Proveedor (Nuevo)
    provider = models.ForeignKey(Provider, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')

    # Para Transferencias
    transfer_destination_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='incoming_transfers')
    
    # Metadatos opcionales
    client_name = models.CharField("Cliente / Tercero", max_length=200, blank=True, null=True) 
    date = models.DateField("Fecha Movimiento")
    
    # Vinculación opcional con Pedidos
    related_order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='accounting_entries')
    
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        # Recuperar estado anterior si es edición (simple logic for now)
        # Por ahora asumiremos lógica simple: Insertar suma/resta
        
        super().save(*args, **kwargs)
        
        # Actualizar saldo de cuenta (lógica simple, se refinará después)
        # Nota: Idealmente esto iría en signals.py para manejar deletes/updates complejos
    
    def __str__(self):
        return f"{self.date} - {self.description} (${self.amount})"


class Debt(models.Model):
    """
    Deuda con un proveedor
    """
    STATUS_CHOICES = (
        ('open', 'Abierta'),
        ('partial', 'Pago Parcial'),
        ('paid', 'Pagada'),
    )
    
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='debts', verbose_name="Proveedor")
    total_amount = models.DecimalField("Monto Total", max_digits=12, decimal_places=2)
    description = models.TextField("Descripción / Concepto")
    status = models.CharField("Estado", max_length=20, choices=STATUS_CHOICES, default='open')
    date_created = models.DateField("Fecha de Creación")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def get_total_paid(self):
        """Calcula el total abonado"""
        from django.db.models import Sum
        total = self.payments.aggregate(total=Sum('amount'))['total']
        return total or 0
    
    def get_remaining(self):
        """Calcula el saldo pendiente"""
        return self.total_amount - self.get_total_paid()
    
    def get_progress_percentage(self):
        """Calcula el porcentaje pagado"""
        if self.total_amount == 0:
            return 0
        return int((self.get_total_paid() / self.total_amount) * 100)
    
    def update_status(self):
        """Actualiza el estado basado en los abonos"""
        remaining = self.get_remaining()
        if remaining <= 0:
            self.status = 'paid'
        elif remaining < self.total_amount:
            self.status = 'partial'
        else:
            self.status = 'open'
        self.save()
    
    def __str__(self):
        return f"{self.provider.name} - ${self.total_amount} ({self.get_status_display()})"


class Payment(models.Model):
    """
    Abono/pago a una deuda
    """
    debt = models.ForeignKey(Debt, on_delete=models.CASCADE, related_name='payments', verbose_name="Deuda")
    amount = models.DecimalField("Monto Abonado", max_digits=12, decimal_places=2)
    payment_date = models.DateField("Fecha de Pago")
    notes = models.TextField("Notas", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Actualizar automáticamente el estado de la deuda
        self.debt.update_status()
    
    def __str__(self):
        return f"Abono ${self.amount} - {self.debt.provider.name} ({self.payment_date})"


class Invoice(models.Model):
    number = models.CharField("Número", max_length=20, unique=True)
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='invoices',
        verbose_name="Cliente"
    )
    client_name = models.CharField("Nombre del Cliente", max_length=200, blank=True)
    client_address = models.TextField("Dirección del Cliente", blank=True)
    date = models.DateField("Fecha de Emisión")
    notes = models.TextField("Notas", blank=True)
    discount = models.DecimalField("Descuento Global", max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_subtotal(self):
        from django.db.models import Sum, F
        result = self.items.aggregate(
            total=Sum(F('quantity') * F('unit_price'))
        )['total']
        return result or 0

    def get_total(self):
        return self.get_subtotal() - self.discount

    @staticmethod
    def get_next_number():
        last = Invoice.objects.order_by('-id').first()
        if last:
            try:
                last_num = int(last.number.replace('FAC-', ''))
                return f"FAC-{last_num + 1:04d}"
            except ValueError:
                pass
        return "FAC-0001"

    def __str__(self):
        return f"{self.number} - {self.client_name or 'Sin cliente'}"

    class Meta:
        ordering = ['-date', '-created_at']


class ShippingObservation(models.Model):
    text = models.CharField("Observación", max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.text

    class Meta:
        ordering = ['text']


class ShippingGuide(models.Model):
    number = models.CharField("Número", max_length=20, unique=True)
    # Remitente
    sender_name = models.CharField("Nombre Remitente", max_length=100)
    sender_lastname = models.CharField("Apellido Remitente", max_length=100)
    sender_cedula = models.CharField("Cédula Remitente", max_length=20, blank=True)
    sender_phone = models.CharField("Celular Remitente", max_length=20)
    sender_department = models.CharField("Departamento Remitente", max_length=100, blank=True)
    sender_city = models.CharField("Ciudad Remitente", max_length=100)
    sender_address = models.CharField("Dirección Remitente", max_length=255)
    # Destinatario
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='shipping_guides',
        verbose_name="Cliente"
    )
    recipient_name = models.CharField("Nombre Destinatario", max_length=100)
    recipient_lastname = models.CharField("Apellido Destinatario", max_length=100)
    recipient_cedula = models.CharField("Cédula Destinatario", max_length=20, blank=True)
    recipient_phone = models.CharField("Celular Destinatario", max_length=20)
    recipient_department = models.CharField("Departamento Destinatario", max_length=100, blank=True)
    recipient_city = models.CharField("Ciudad Destinatario", max_length=100)
    recipient_address = models.CharField("Dirección Destinatario", max_length=255)
    # Extras
    collection_value = models.DecimalField("Valor a Recaudar", max_digits=12, decimal_places=2, default=0, blank=True)
    observation = models.TextField("Observación", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def get_next_number():
        last = ShippingGuide.objects.order_by('-id').first()
        if last:
            try:
                last_num = int(last.number.replace('GE-', ''))
                return f"GE-{last_num + 1:04d}"
            except ValueError:
                pass
        return "GE-0001"

    def __str__(self):
        return f"{self.number} - {self.sender_name} → {self.recipient_name}"

    class Meta:
        ordering = ['-created_at']


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items', verbose_name="Factura")
    description = models.CharField("Descripción", max_length=255)
    quantity = models.DecimalField("Cantidad", max_digits=10, decimal_places=2)
    unit_price = models.DecimalField("Precio Unitario", max_digits=12, decimal_places=2)

    def get_total(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.description} x{self.quantity}"
