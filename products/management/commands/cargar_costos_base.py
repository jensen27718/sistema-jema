"""
Carga datos iniciales para tipos de costo manuales.
Uso: python manage.py cargar_costos_base
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from products.models_costs import CostType


class Command(BaseCommand):
    help = "Carga tipos de costo para el registro manual de gastos por pedido"

    def handle(self, *args, **options):
        self.stdout.write("Cargando tipos de costo base...")

        cost_types_data = [
            {
                "name": "Descartonado",
                "unit": "unidad",
                "default_unit_price": Decimal("100"),
                "description": "Costo de referencia por descartonado",
            },
            {
                "name": "Material Vinilo",
                "unit": "metro_lineal",
                "default_unit_price": Decimal("0"),
                "description": "Costo de referencia para material vinilo",
            },
            {
                "name": "Transfer",
                "unit": "metro_lineal",
                "default_unit_price": Decimal("0"),
                "description": "Costo de referencia para transfer",
            },
            {
                "name": "Impresion",
                "unit": "metro_cuadrado",
                "default_unit_price": Decimal("0"),
                "description": "Costo de referencia para impresion",
            },
            {
                "name": "Material Cinta",
                "unit": "metro_lineal",
                "default_unit_price": Decimal("0"),
                "description": "Costo de referencia para cinta",
            },
        ]

        for data in cost_types_data:
            ct, created = CostType.objects.get_or_create(name=data["name"], defaults=data)
            status = "CREADO" if created else "ya existe"
            self.stdout.write(f"  - {ct.name}: {status}")

        self.stdout.write(
            self.style.SUCCESS(
                "\nTipos de costo cargados correctamente. "
                "El sistema de calculo automatico fue retirado."
            )
        )
