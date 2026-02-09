"""
Servicios de cálculo para Job Costing — Overhead, Utilidad, Distribución
"""
from datetime import date, timedelta, datetime
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone


def get_or_create_current_week():
    """Retorna/crea la FinancialWeek del lunes actual"""
    from contabilidad.models_job_costing import FinancialWeek

    today = date.today()
    # Lunes de esta semana
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    iso_year, iso_week, _ = monday.isocalendar()

    week, _ = FinancialWeek.objects.get_or_create(
        year=iso_year,
        week_number=iso_week,
        defaults={
            'start_date': monday,
            'end_date': sunday,
        }
    )
    return week


def get_week_for_date(target_date):
    """Retorna/crea la FinancialWeek para una fecha dada"""
    from contabilidad.models_job_costing import FinancialWeek

    monday = target_date - timedelta(days=target_date.weekday())
    sunday = monday + timedelta(days=6)
    iso_year, iso_week, _ = monday.isocalendar()

    week, _ = FinancialWeek.objects.get_or_create(
        year=iso_year,
        week_number=iso_week,
        defaults={
            'start_date': monday,
            'end_date': sunday,
        }
    )
    return week


def ensure_financial_status(order=None, internal_order=None):
    """get_or_create FinancialStatus para un pedido"""
    from contabilidad.models_job_costing import FinancialStatus

    if order:
        fs, created = FinancialStatus.objects.get_or_create(
            order=order,
            defaults={
                'sale_amount': order.total or 0,
                'state': 'cobrado' if order.is_paid else 'creado',
            }
        )
    elif internal_order:
        state = 'creado'
        if internal_order.status == 'completed':
            state = 'cobrado'
        elif internal_order.status == 'cancelled':
            state = 'cancelado'
        elif internal_order.status in ('confirmed', 'in_production'):
            state = 'enviado'

        fs, created = FinancialStatus.objects.get_or_create(
            internal_order=internal_order,
            defaults={
                'sale_amount': internal_order.total_estimated or 0,
                'state': state,
            }
        )
    else:
        raise ValueError("Debe proporcionar order o internal_order")

    return fs


def transition_financial_state(financial_status, new_state, user=None):
    """
    Transiciona el estado financiero validando transiciones permitidas.
    Retorna (success: bool, message: str)
    """
    VALID_TRANSITIONS = {
        'creado': ['enviado', 'cancelado'],
        'enviado': ['cobrado', 'cancelado'],
        'cobrado': ['cancelado'],
        'cancelado': [],
    }

    current = financial_status.state
    allowed = VALID_TRANSITIONS.get(current, [])

    if new_state not in allowed:
        return False, f"No se puede pasar de '{current}' a '{new_state}'"

    now = timezone.now()
    financial_status.state = new_state

    if new_state == 'enviado':
        financial_status.sent_at = now
    elif new_state == 'cobrado':
        financial_status.collected_at = now
        # Sincronizar is_paid en Order
        if financial_status.order:
            financial_status.order.is_paid = True
            financial_status.order.save(update_fields=['is_paid'])
    elif new_state == 'cancelado':
        financial_status.cancelled_at = now

    financial_status.save()
    return True, f"Estado cambiado a '{new_state}'"


def get_direct_costs_for_order(financial_status):
    """Suma costos directos (OrderCostBreakdown) del pedido"""
    from products.models_costs import OrderCostBreakdown

    filters = {}
    if financial_status.order:
        filters['order'] = financial_status.order
    elif financial_status.internal_order:
        filters['internal_order'] = financial_status.internal_order
    else:
        return Decimal('0')

    result = OrderCostBreakdown.objects.filter(**filters).aggregate(
        total=Sum('total')
    )['total']
    return result or Decimal('0')


def get_shipping_cost_for_order(financial_status):
    """Obtiene costo de envío del pedido"""
    if financial_status.order:
        return financial_status.order.shipping_cost or Decimal('0')
    elif financial_status.internal_order:
        return financial_status.internal_order.shipping_cost or Decimal('0')
    return Decimal('0')


def calculate_weekly_overhead(week, cutoff_date=None):
    """
    Calcula overhead semanal:
    overhead_% = gastos_fijos / ventas_cobradas

    cutoff_date:
        - None: usa toda la semana (lunes a domingo)
        - date: usa semana acumulada hasta esa fecha
    """
    from contabilidad.models import Transaction, TransactionCategory
    from contabilidad.models_job_costing import FinancialStatus

    period_end = week.end_date
    if cutoff_date:
        period_end = min(week.end_date, cutoff_date)

    # Gastos fijos de la semana
    fixed_costs = Transaction.objects.filter(
        category__is_fixed_cost=True,
        category__transaction_type='egreso',
        date__gte=week.start_date,
        date__lte=period_end,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    # Ventas cobradas en la semana
    collected_statuses = FinancialStatus.objects.filter(
        state='cobrado',
        collected_at__date__gte=week.start_date,
        collected_at__date__lte=period_end,
    )
    total_sales = collected_statuses.aggregate(
        total=Sum('sale_amount')
    )['total'] or Decimal('0')

    if total_sales > 0:
        overhead_pct = (fixed_costs / total_sales) * 100
    else:
        overhead_pct = Decimal('0')

    return {
        'fixed_costs': fixed_costs,
        'total_sales': total_sales,
        'overhead_percentage': overhead_pct,
        'collected_statuses': collected_statuses,
    }


def calculate_order_profit(financial_status, overhead_pct):
    """Calcula utilidad de un pedido dado un % de overhead"""
    sale = financial_status.sale_amount or Decimal('0')
    direct_costs = get_direct_costs_for_order(financial_status)
    shipping = get_shipping_cost_for_order(financial_status)
    overhead_amount = (sale * overhead_pct / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    net_profit = sale - direct_costs - shipping - overhead_amount

    return {
        'sale_amount': sale,
        'direct_costs': direct_costs,
        'shipping_cost': shipping,
        'overhead_percentage': overhead_pct,
        'overhead_amount': overhead_amount,
        'net_profit': net_profit,
    }


@db_transaction.atomic
def close_financial_week(week, user=None):
    """
    Cierra la semana financiera:
    1. Calcula overhead
    2. Crea snapshots por pedido cobrado
    3. Calcula distribuciones
    4. Crea transacciones contables
    """
    from contabilidad.models_job_costing import (
        JobCostingConfig, OrderFinancialSnapshot, PartnerDistribution, Partner
    )
    from contabilidad.models import Transaction, TransactionCategory

    if week.status == 'closed':
        return False, "La semana ya está cerrada"

    config = JobCostingConfig.get_config()

    # 1. Calcular overhead
    overhead_data = calculate_weekly_overhead(week)
    overhead_pct = overhead_data['overhead_percentage']
    collected_statuses = overhead_data['collected_statuses']

    # 2. Crear snapshots por pedido
    total_net_profit = Decimal('0')
    total_direct_costs = Decimal('0')
    total_overhead_applied = Decimal('0')
    order_count = 0

    for fs in collected_statuses:
        # Evitar duplicados
        if hasattr(fs, 'financial_snapshot'):
            continue

        profit_data = calculate_order_profit(fs, overhead_pct)

        OrderFinancialSnapshot.objects.create(
            financial_week=week,
            financial_status=fs,
            sale_amount=profit_data['sale_amount'],
            direct_costs=profit_data['direct_costs'],
            shipping_cost=profit_data['shipping_cost'],
            overhead_percentage=profit_data['overhead_percentage'],
            overhead_amount=profit_data['overhead_amount'],
            net_profit=profit_data['net_profit'],
        )

        total_net_profit += profit_data['net_profit']
        total_direct_costs += profit_data['direct_costs'] + profit_data['shipping_cost']
        total_overhead_applied += profit_data['overhead_amount']
        order_count += 1

    # 3. Calcular distribución
    savings_pct = config.savings_percentage / Decimal('100')
    distribution_pct = config.distribution_percentage / Decimal('100')

    # Solo distribuir utilidad positiva
    distributable_profit = max(total_net_profit, Decimal('0'))
    savings_amount = (distributable_profit * savings_pct).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    distributable_amount = (distributable_profit * distribution_pct).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # 4. Crear distribuciones por socio
    active_partners = Partner.objects.filter(is_active=True)
    for partner in active_partners:
        partner_amount = (distributable_amount * partner.share_percentage / Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        PartnerDistribution.objects.get_or_create(
            financial_week=week,
            partner=partner,
            defaults={
                'share_percentage': partner.share_percentage,
                'gross_amount': partner_amount,
            }
        )

    # 5. Crear transacciones contables si hay cuentas configuradas
    today = date.today()

    # Categoría genérica para transacciones auto-generadas
    cat_ingreso, _ = TransactionCategory.objects.get_or_create(
        name='Job Costing - Distribución',
        defaults={'transaction_type': 'egreso'}
    )

    if config.cuenta_ahorro and savings_amount > 0:
        Transaction.objects.create(
            account=config.cuenta_ahorro,
            category=cat_ingreso,
            amount=savings_amount,
            description=f"Ahorro empresa — Semana {week.week_number}/{week.year}",
            date=today,
            financial_week=week,
        )

    if config.cuenta_distribucion and distributable_amount > 0:
        Transaction.objects.create(
            account=config.cuenta_distribucion,
            category=cat_ingreso,
            amount=distributable_amount,
            description=f"Distribución socios — Semana {week.week_number}/{week.year}",
            date=today,
            financial_week=week,
        )

    # 6. Actualizar snapshot de la semana
    week.total_sales = overhead_data['total_sales']
    week.total_direct_costs = total_direct_costs
    week.total_fixed_costs = overhead_data['fixed_costs']
    week.overhead_percentage = overhead_pct
    week.total_overhead_applied = total_overhead_applied
    week.total_net_profit = total_net_profit
    week.savings_amount = savings_amount
    week.distributable_amount = distributable_amount
    week.orders_count = order_count
    week.status = 'closed'
    week.closed_at = timezone.now()
    week.closed_by = user
    week.save()

    return True, f"Semana {week.week_number}/{week.year} cerrada con {order_count} pedidos"


def get_live_overhead_preview():
    """Preview en tiempo real de la semana abierta (read-only)"""
    week = get_or_create_current_week()

    if week.status == 'closed':
        return {
            'week': week,
            'is_closed': True,
            'overhead_percentage': week.overhead_percentage,
            'total_sales': week.total_sales,
            'fixed_costs': week.total_fixed_costs,
            'total_net_profit': week.total_net_profit,
            'orders_count': week.orders_count,
        }

    # Live diario: acumula desde lunes hasta hoy (no hasta domingo)
    today = date.today()
    overhead_data = calculate_weekly_overhead(week, cutoff_date=today)
    collected_statuses = overhead_data['collected_statuses']

    # Calcular utilidad estimada
    total_net_profit = Decimal('0')
    order_details = []
    for fs in collected_statuses:
        profit_data = calculate_order_profit(fs, overhead_data['overhead_percentage'])
        total_net_profit += profit_data['net_profit']
        order_details.append({
            'financial_status': fs,
            **profit_data,
        })

    return {
        'week': week,
        'is_closed': False,
        'overhead_percentage': overhead_data['overhead_percentage'],
        'total_sales': overhead_data['total_sales'],
        'fixed_costs': overhead_data['fixed_costs'],
        'as_of_date': today,
        'total_net_profit': total_net_profit,
        'orders_count': collected_statuses.count(),
        'order_details': order_details,
    }


@db_transaction.atomic
def pay_partner_distribution(distribution, account, user=None):
    """Marca distribución como pagada y crea Transaction"""
    from contabilidad.models import Transaction, TransactionCategory

    if distribution.status == 'paid':
        return False, "Esta distribución ya fue pagada"

    cat, _ = TransactionCategory.objects.get_or_create(
        name='Job Costing - Pago Socio',
        defaults={'transaction_type': 'egreso'}
    )

    txn = Transaction.objects.create(
        account=account,
        category=cat,
        amount=distribution.gross_amount,
        description=f"Pago a {distribution.partner.name} — Sem {distribution.financial_week.week_number}/{distribution.financial_week.year}",
        date=date.today(),
        financial_week=distribution.financial_week,
    )

    distribution.status = 'paid'
    distribution.transaction = txn
    distribution.paid_at = timezone.now()
    distribution.save()

    return True, f"Pago de ${distribution.gross_amount} a {distribution.partner.name} registrado"
