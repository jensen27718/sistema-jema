"""
Management command para configurar Job Costing:
- Crea cuentas (bolsas) si no existen
- Crea JobCostingConfig singleton
- Crea 2 socios default (50/50)
- Marca categorías de egreso comunes como gasto fijo
- Crea FinancialStatus retroactivo para pedidos existentes
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Configura datos iniciales para Job Costing (idempotente)'

    def handle(self, *args, **options):
        from contabilidad.models import Account, TransactionCategory
        from contabilidad.models_job_costing import (
            JobCostingConfig, Partner, FinancialStatus
        )
        from contabilidad.job_costing_services import (
            ensure_financial_status,
            sync_internal_order_financial_status,
        )
        from products.models import Order
        from products.models_internal_orders import InternalOrder

        self.stdout.write('=== Setup Job Costing ===\n')

        # 1. Crear cuentas
        cuentas = {
            'principal': 'JC - Principal',
            'costos': 'JC - Reserva Costos',
            'ahorro': 'JC - Ahorro Empresa',
            'distribucion': 'JC - Distribucion Socios',
        }
        accounts = {}
        for key, name in cuentas.items():
            acc, created = Account.objects.get_or_create(
                name=name,
                defaults={'description': f'Cuenta auto-creada para Job Costing ({key})'}
            )
            accounts[key] = acc
            status = 'CREADA' if created else 'ya existe'
            self.stdout.write(f'  Cuenta "{name}": {status}')

        # 2. Configuración singleton
        config = JobCostingConfig.get_config()
        if not config.cuenta_principal:
            config.cuenta_principal = accounts['principal']
            config.cuenta_costos = accounts['costos']
            config.cuenta_ahorro = accounts['ahorro']
            config.cuenta_distribucion = accounts['distribucion']
            config.save()
            self.stdout.write('  Config vinculada a cuentas')
        else:
            self.stdout.write('  Config ya tiene cuentas asignadas')

        # 3. Socios default
        if Partner.objects.count() == 0:
            Partner.objects.create(name='Socio 1', share_percentage=50)
            Partner.objects.create(name='Socio 2', share_percentage=50)
            self.stdout.write('  2 socios creados (50/50)')
        else:
            self.stdout.write(f'  {Partner.objects.count()} socios ya existen')

        # 4. Marcar categorías de egreso comunes como gasto fijo
        keywords = ['arriendo', 'renta', 'alquiler', 'servicios', 'internet',
                     'agua', 'luz', 'energia', 'telefono', 'nomina', 'salario',
                     'seguro', 'contador', 'contabilidad']
        marked = 0
        for cat in TransactionCategory.objects.filter(transaction_type='egreso'):
            name_lower = cat.name.lower()
            if any(kw in name_lower for kw in keywords) and not cat.is_fixed_cost:
                cat.is_fixed_cost = True
                cat.save(update_fields=['is_fixed_cost'])
                marked += 1
                self.stdout.write(f'  Categoria "{cat.name}" marcada como gasto fijo')
        if marked == 0:
            self.stdout.write('  No se encontraron categorias para marcar como gasto fijo')

        # 5. Retroactivar FinancialStatus para pedidos existentes
        created_orders = 0
        for order in Order.objects.all():
            existed = FinancialStatus.objects.filter(order=order).exists()
            ensure_financial_status(order=order)
            if not existed:
                created_orders += 1
        self.stdout.write(f'  FinancialStatus creados para {created_orders} pedidos de catalogo')

        created_internal = 0
        for io in InternalOrder.objects.all():
            existed = FinancialStatus.objects.filter(internal_order=io).exists()
            sync_internal_order_financial_status(io, allow_downgrade=True)
            if not existed:
                created_internal += 1
        self.stdout.write(f'  FinancialStatus creados para {created_internal} pedidos internos')

        self.stdout.write(self.style.SUCCESS('\nSetup completado exitosamente!'))
