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
