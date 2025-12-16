# products/management/commands/setup_attributes.py
from django.core.management.base import BaseCommand
from products.models import Size, Material, Color

class Command(BaseCommand):
    help = 'Carga los atributos base (Tamaños, Colores, Materiales)'

    def handle(self, *args, **kwargs):
        # 1. Crear Tamaños
        sizes = [
            ("Grande", "19x25cm"),
            ("Mediano", "19x15cm"),
            ("Pequeño", "14,5x14,3cm")
        ]
        for name, dim in sizes:
            Size.objects.get_or_create(name=name, dimensions=dim)
            self.stdout.write(f"Tamaño creado: {name}")

        # 2. Crear Materiales
        Material.objects.get_or_create(name="Vinilo Tradicional", is_special=False)
        Material.objects.get_or_create(name="Mailan Metalizado", is_special=True)
        self.stdout.write("Materiales creados")

        # 3. Crear Colores Base
        colors = ["Azul", "Blanco", "Dorado", "Negro", "Rojo", "Rosado", "Lila"]
        for c in colors:
            Color.objects.get_or_create(name=c)
            self.stdout.write(f"Color creado: {c}")