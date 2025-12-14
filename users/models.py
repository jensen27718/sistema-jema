from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    # Definimos roles
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        EMPLOYEE = "EMPLOYEE", "Empleado"
        CUSTOMER = "CUSTOMER", "Cliente"

    role = models.CharField(max_length=50, choices=Role.choices, default=Role.CUSTOMER)
    
    # Aquí puedes agregar campos extras que todos tengan
    phone_number = models.CharField(max_length=15, blank=True, null=True)

    def save(self, *args, **kwargs):
        # Si es superusuario, forzar rol de ADMIN
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username