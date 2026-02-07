"""
Vistas para Job Costing — Dashboard, Semanas, Pedidos, Socios, Config
"""
import json
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator

from contabilidad.models import Account
from contabilidad.models_job_costing import (
    JobCostingConfig, Partner, FinancialStatus,
    FinancialWeek, OrderFinancialSnapshot, PartnerDistribution,
)
from contabilidad import job_costing_services as jc_services


def is_staff(user):
    return user.is_staff or user.is_superuser


# ─── Dashboard ───────────────────────────────────────────────

@login_required
@user_passes_test(is_staff)
def job_costing_dashboard_view(request):
    preview = jc_services.get_live_overhead_preview()
    week = preview['week']

    # Últimas semanas cerradas
    closed_weeks = FinancialWeek.objects.filter(status='closed').order_by('-year', '-week_number')[:5]

    # Ahorro acumulado
    from django.db.models import Sum
    total_savings = FinancialWeek.objects.filter(status='closed').aggregate(
        total=Sum('savings_amount')
    )['total'] or Decimal('0')

    # Socios activos
    partners = Partner.objects.filter(is_active=True)

    context = {
        'preview': preview,
        'week': week,
        'closed_weeks': closed_weeks,
        'total_savings': total_savings,
        'partners': partners,
    }
    return render(request, 'contabilidad/job_costing/dashboard.html', context)


# ─── Detalle de Semana ───────────────────────────────────────

@login_required
@user_passes_test(is_staff)
def financial_week_detail_view(request, year, week_number):
    week = get_object_or_404(FinancialWeek, year=year, week_number=week_number)
    snapshots = week.order_snapshots.select_related(
        'financial_status', 'financial_status__order', 'financial_status__internal_order'
    ).all()
    distributions = week.distributions.select_related('partner').all()

    accounts = Account.objects.all()

    context = {
        'week': week,
        'snapshots': snapshots,
        'distributions': distributions,
        'accounts': accounts,
    }
    return render(request, 'contabilidad/job_costing/week_detail.html', context)


# ─── Cerrar Semana ───────────────────────────────────────────

@login_required
@user_passes_test(is_staff)
def close_week_view(request):
    if request.method == 'POST':
        week = jc_services.get_or_create_current_week()
        success, msg = jc_services.close_financial_week(week, user=request.user)
        if success:
            messages.success(request, msg)
        else:
            messages.warning(request, msg)
        return redirect('job_costing_dashboard')
    return redirect('job_costing_dashboard')


# ─── Lista de Pedidos Financieros ────────────────────────────

@login_required
@user_passes_test(is_staff)
def financial_orders_list_view(request):
    qs = FinancialStatus.objects.select_related('order', 'internal_order').all()

    state_filter = request.GET.get('state', '')
    if state_filter:
        qs = qs.filter(state=state_filter)

    paginator = Paginator(qs, 25)
    page = request.GET.get('page', 1)
    statuses = paginator.get_page(page)

    context = {
        'statuses': statuses,
        'state_filter': state_filter,
        'state_choices': FinancialStatus.STATE_CHOICES,
    }
    return render(request, 'contabilidad/job_costing/orders_list.html', context)


# ─── Socios ──────────────────────────────────────────────────

@login_required
@user_passes_test(is_staff)
def partner_list_view(request):
    from django.db.models import Sum
    partners = Partner.objects.all()
    total_pct = partners.filter(is_active=True).aggregate(
        total=Sum('share_percentage')
    )['total'] or Decimal('0')

    context = {
        'partners': partners,
        'total_pct': total_pct,
    }
    return render(request, 'contabilidad/job_costing/partners.html', context)


@login_required
@user_passes_test(is_staff)
def partner_create_update_view(request, partner_id=None):
    partner = get_object_or_404(Partner, id=partner_id) if partner_id else None

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        share_pct = request.POST.get('share_percentage', '0')
        is_active = request.POST.get('is_active') == 'on'

        if not name:
            messages.error(request, "El nombre es obligatorio.")
            return render(request, 'contabilidad/job_costing/partner_form.html', {'partner': partner})

        if partner:
            partner.name = name
            partner.share_percentage = Decimal(share_pct)
            partner.is_active = is_active
            partner.save()
            messages.success(request, f"Socio '{name}' actualizado.")
        else:
            Partner.objects.create(
                name=name,
                share_percentage=Decimal(share_pct),
                is_active=is_active,
            )
            messages.success(request, f"Socio '{name}' creado.")

        return redirect('job_costing_partners')

    context = {'partner': partner}
    return render(request, 'contabilidad/job_costing/partner_form.html', context)


# ─── Configuración ───────────────────────────────────────────

@login_required
@user_passes_test(is_staff)
def job_costing_config_view(request):
    config = JobCostingConfig.get_config()
    accounts = Account.objects.all()

    if request.method == 'POST':
        config.savings_percentage = Decimal(request.POST.get('savings_percentage', '5'))
        config.distribution_percentage = Decimal(request.POST.get('distribution_percentage', '95'))

        cuenta_principal_id = request.POST.get('cuenta_principal')
        cuenta_costos_id = request.POST.get('cuenta_costos')
        cuenta_ahorro_id = request.POST.get('cuenta_ahorro')
        cuenta_distribucion_id = request.POST.get('cuenta_distribucion')

        config.cuenta_principal_id = cuenta_principal_id if cuenta_principal_id else None
        config.cuenta_costos_id = cuenta_costos_id if cuenta_costos_id else None
        config.cuenta_ahorro_id = cuenta_ahorro_id if cuenta_ahorro_id else None
        config.cuenta_distribucion_id = cuenta_distribucion_id if cuenta_distribucion_id else None

        config.save()
        messages.success(request, "Configuración actualizada.")
        return redirect('job_costing_config')

    context = {
        'config': config,
        'accounts': accounts,
    }
    return render(request, 'contabilidad/job_costing/config.html', context)


# ─── Pagar Distribución ─────────────────────────────────────

@login_required
@user_passes_test(is_staff)
def pay_distribution_view(request, distribution_id):
    distribution = get_object_or_404(PartnerDistribution, id=distribution_id)

    if request.method == 'POST':
        account_id = request.POST.get('account_id')
        if not account_id:
            messages.error(request, "Selecciona una cuenta para el pago.")
        else:
            account = get_object_or_404(Account, id=account_id)
            success, msg = jc_services.pay_partner_distribution(distribution, account, user=request.user)
            if success:
                messages.success(request, msg)
            else:
                messages.warning(request, msg)

    return redirect('job_costing_week_detail',
                    year=distribution.financial_week.year,
                    week_number=distribution.financial_week.week_number)


# ─── APIs JSON ───────────────────────────────────────────────

@login_required
@user_passes_test(is_staff)
def api_transition_financial_state(request):
    """POST: {financial_status_id, new_state}"""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST requerido'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    fs_id = data.get('financial_status_id')
    new_state = data.get('new_state')

    if not fs_id or not new_state:
        return JsonResponse({'ok': False, 'error': 'Parámetros faltantes'}, status=400)

    try:
        fs = FinancialStatus.objects.get(id=fs_id)
    except FinancialStatus.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Estado financiero no encontrado'}, status=404)

    success, msg = jc_services.transition_financial_state(fs, new_state, user=request.user)

    return JsonResponse({
        'ok': success,
        'message': msg,
        'new_state': fs.state,
        'badge_class': fs.get_state_badge_class(),
    })


@login_required
@user_passes_test(is_staff)
def api_order_profitability(request):
    """GET: ?financial_status_id=X"""
    fs_id = request.GET.get('financial_status_id')
    if not fs_id:
        return JsonResponse({'ok': False, 'error': 'financial_status_id requerido'}, status=400)

    try:
        fs = FinancialStatus.objects.get(id=fs_id)
    except FinancialStatus.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'No encontrado'}, status=404)

    # Usar overhead live de la semana actual
    preview = jc_services.get_live_overhead_preview()
    overhead_pct = preview['overhead_percentage']

    profit_data = jc_services.calculate_order_profit(fs, overhead_pct)

    return JsonResponse({
        'ok': True,
        'sale_amount': str(profit_data['sale_amount']),
        'direct_costs': str(profit_data['direct_costs']),
        'shipping_cost': str(profit_data['shipping_cost']),
        'overhead_percentage': str(profit_data['overhead_percentage']),
        'overhead_amount': str(profit_data['overhead_amount']),
        'net_profit': str(profit_data['net_profit']),
    })
