"""
Carga datos iniciales para el sistema de costos de producción.
Uso: python manage.py cargar_costos_base
"""
from django.core.management.base import BaseCommand
from decimal import Decimal

from products.models_costs import CostType, ProductTypeCostConfig


class Command(BaseCommand):
    help = 'Carga tipos de costo y configuraciones iniciales'

    def handle(self, *args, **options):
        self.stdout.write("Cargando costos base...")

        # 1. Tipos de Costo
        cost_types_data = [
            {
                'name': 'Descartonado',
                'unit': 'unidad',
                'default_unit_price': Decimal('100'),
                'description': 'Costo por unidad de descartonado',
            },
            {
                'name': 'Material Vinilo',
                'unit': 'metro_lineal',
                'default_unit_price': Decimal('0'),
                'description': 'Costo por metro lineal de vinilo',
            },
            {
                'name': 'Transfer',
                'unit': 'metro_lineal',
                'default_unit_price': Decimal('0'),
                'description': 'Costo por metro lineal de transfer',
            },
            {
                'name': 'Impresión',
                'unit': 'metro_cuadrado',
                'default_unit_price': Decimal('0'),
                'description': 'Costo por metro cuadrado de impresión',
            },
            {
                'name': 'Material Cinta',
                'unit': 'metro_lineal',
                'default_unit_price': Decimal('0'),
                'description': 'Costo por metro lineal de cinta',
            },
        ]

        created_types = {}
        for data in cost_types_data:
            ct, created = CostType.objects.get_or_create(
                name=data['name'],
                defaults=data,
            )
            created_types[data['name']] = ct
            status = "CREADO" if created else "ya existe"
            self.stdout.write(f"  - {ct.name}: {status}")

        # 2. Configuraciones por tipo de producto
        configs_data = [
            {
                'product_type': 'vinilo_corte',
                'cost_type_name': 'Descartonado',
                'calculation_method': 'per_unit',
                'material_width_cm': None,
                'position': 0,
            },
            {
                'product_type': 'vinilo_corte',
                'cost_type_name': 'Material Vinilo',
                'calculation_method': 'linear_meters',
                'material_width_cm': Decimal('60'),
                'position': 1,
            },
            {
                'product_type': 'vinilo_corte',
                'cost_type_name': 'Transfer',
                'calculation_method': 'linear_meters',
                'material_width_cm': Decimal('60'),
                'position': 2,
            },
            {
                'product_type': 'impreso_globo',
                'cost_type_name': 'Impresión',
                'calculation_method': 'square_meters',
                'material_width_cm': None,
                'position': 0,
            },
            {
                'product_type': 'cinta',
                'cost_type_name': 'Material Cinta',
                'calculation_method': 'linear_meters',
                'material_width_cm': Decimal('60'),
                'position': 0,
            },
        ]

        for data in configs_data:
            cost_type = created_types.get(data['cost_type_name'])
            if not cost_type:
                self.stdout.write(self.style.WARNING(f"  ! Tipo de costo '{data['cost_type_name']}' no encontrado"))
                continue

            config, created = ProductTypeCostConfig.objects.get_or_create(
                product_type=data['product_type'],
                cost_type=cost_type,
                defaults={
                    'calculation_method': data['calculation_method'],
                    'material_width_cm': data['material_width_cm'],
                    'position': data['position'],
                }
            )
            status = "CREADO" if created else "ya existe"
            self.stdout.write(f"  - {data['product_type']} -> {data['cost_type_name']}: {status}")

        self.stdout.write(self.style.SUCCESS("\nCostos base cargados correctamente."))
