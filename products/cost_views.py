"""
Vistas y APIs para el sistema de costos de producción.
"""
import json
import logging
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST

from products.models import Product, ProductVariant, Order
from products.models_internal_orders import InternalOrder
from products.models_costs import CostType, ProductTypeCostConfig, OrderCostBreakdown
from products.cost_services import calculate_order_costs

logger = logging.getLogger(__name__)


def is_staff(user):
    return user.is_staff


# ========================
# PÁGINA DE CONFIGURACIÓN
# ========================

@login_required
@user_passes_test(is_staff)
def cost_config_view(request):
    """Página de configuración de tipos de costo y asignación por tipo de producto"""
    cost_types = CostType.objects.all()
    product_types = Product.TYPE_CHOICES

    # Obtener configs agrupadas por product_type
    configs_by_type = {}
    for code, label in product_types:
        configs_by_type[code] = {
            'label': label,
            'configs': list(
                ProductTypeCostConfig.objects.filter(product_type=code)
                .select_related('cost_type')
                .order_by('position')
            ),
        }

    return render(request, 'dashboard/costs/config.html', {
        'cost_types': cost_types,
        'product_types': product_types,
        'configs_by_type': configs_by_type,
        'calc_methods': ProductTypeCostConfig.CALC_METHOD_CHOICES,
    })


# ========================
# CRUD TIPOS DE COSTO
# ========================

@login_required
@user_passes_test(is_staff)
@require_POST
def api_create_cost_type(request):
    """Crear un nuevo tipo de costo"""
    try:
        data = json.loads(request.body)
        val = data.get('default_unit_price')
        if val in (None, ''):
            val = 0
            
        ct = CostType.objects.create(
            name=data.get('name', ''),
            unit=data.get('unit', 'unidad'),
            default_unit_price=Decimal(str(val).replace(',', '.')),
            description=data.get('description', ''),
            is_active=data.get('is_active', True),
        )
        return JsonResponse({
            'ok': True,
            'id': ct.id,
            'name': ct.name,
            'unit': ct.unit,
            'unit_display': ct.get_unit_display(),
            'default_unit_price': str(ct.default_unit_price),
            'is_active': ct.is_active,
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_update_cost_type(request):
    """Actualizar un tipo de costo"""
    try:
        data = json.loads(request.body)
        ct = get_object_or_404(CostType, id=data.get('id'))
        if 'name' in data:
            ct.name = data['name']
        if 'unit' in data:
            ct.unit = data['unit']
        if 'default_unit_price' in data:
            val = data['default_unit_price']
            ct.default_unit_price = Decimal(str(val).replace(',', '.')) if val not in (None, '') else 0
        if 'description' in data:
            ct.description = data['description']
        if 'is_active' in data:
            ct.is_active = data['is_active']
        if 'special_material_price' in data:
            val = data['special_material_price']
            ct.special_material_price = Decimal(str(val).replace(',', '.')) if val not in (None, '') else 0
        ct.save()
        return JsonResponse({
            'ok': True,
            'id': ct.id,
            'name': ct.name,
            'unit': ct.unit,
            'unit_display': ct.get_unit_display(),
            'default_unit_price': str(ct.default_unit_price),
            'is_active': ct.is_active,
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_delete_cost_type(request):
    """Eliminar un tipo de costo"""
    try:
        data = json.loads(request.body)
        ct = get_object_or_404(CostType, id=data.get('id'))
        ct.delete()
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


# ========================
# ASIGNACIÓN POR TIPO DE PRODUCTO
# ========================

@login_required
@user_passes_test(is_staff)
@require_POST
def api_save_product_type_cost(request):
    """Crear o actualizar una configuración de costo por tipo de producto"""
    try:
        data = json.loads(request.body)
        product_type = data.get('product_type', '')
        cost_type_id = data.get('cost_type_id')
        action = data.get('action', 'save')  # 'save' or 'delete'

        if action == 'delete':
            config_id = data.get('config_id')
            if config_id:
                ProductTypeCostConfig.objects.filter(id=config_id).delete()
            return JsonResponse({'ok': True})

        cost_type = get_object_or_404(CostType, id=cost_type_id)

        config, created = ProductTypeCostConfig.objects.update_or_create(
            product_type=product_type,
            cost_type=cost_type,
            defaults={
                'calculation_method': data.get('calculation_method', 'per_unit'),
                'material_width_cm': Decimal(str(data['material_width_cm']).replace(',', '.')) if data.get('material_width_cm') else None,
                'position': data.get('position', 0),
            }
        )
        return JsonResponse({
            'ok': True,
            'id': config.id,
            'created': created,
            'product_type': config.product_type,
            'cost_type_name': config.cost_type.name,
            'calculation_method': config.calculation_method,
            'material_width_cm': str(config.material_width_cm) if config.material_width_cm else None,
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


# ========================
# CÁLCULO DE COSTOS
# ========================

@login_required
@user_passes_test(is_staff)
@require_POST
def api_calculate_costs(request):
    """Calcular costos de un pedido"""
    order_type = 'unknown'
    order_id = None
    try:
        data = json.loads(request.body)
        order_type = data.get('order_type', 'internal')
        order_id = data.get('order_id')

        if order_type == 'internal':
            order = get_object_or_404(InternalOrder, id=order_id)
        else:
            order = get_object_or_404(Order, id=order_id)

        logger.warning("API costos: iniciando calculo para pedido #%s (%s)", order_id, order_type)
        result = calculate_order_costs(order, order_type)

        breakdowns_data = []
        # Get all breakdowns (including manual ones)
        if order_type == 'internal':
            all_breakdowns = OrderCostBreakdown.objects.filter(
                internal_order=order
            ).select_related('cost_type').order_by('product_type', 'cost_type__name')
        else:
            all_breakdowns = OrderCostBreakdown.objects.filter(
                order=order
            ).select_related('cost_type').order_by('product_type', 'cost_type__name')

        for b in all_breakdowns:
            breakdowns_data.append({
                'id': b.id,
                'cost_type_name': b.cost_type.name,
                'product_type': b.product_type,
                'description': b.description,
                'quantity': str(b.calculated_quantity),
                'unit_price': str(b.unit_price),
                'total': str(b.total),
                'is_manual': b.is_manual,
            })

        diagnostics = result.get('diagnostics', {})
        logger.warning(
            "API costos: pedido #%s (%s) -> breakdowns=%s, total_production=%s, diagnostics=%s",
            order_id,
            order_type,
            len(breakdowns_data),
            result['total_production'],
            diagnostics,
        )

        return JsonResponse({
            'ok': True,
            'breakdowns': breakdowns_data,
            'total_production': str(result['total_production']),
            'total_manual': str(result['total_manual']),
            'shipping': str(result['shipping']),
            'grand_total': str(result['grand_total']),
            'diagnostics': diagnostics,
        })
    except Exception as e:
        logger.exception("API costos: error calculando pedido #%s (%s)", order_id, order_type)
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_update_manual_cost(request):
    """Actualizar un costo manual (cantidad, precio, total)"""
    try:
        data = json.loads(request.body)
        breakdown_id = data.get('breakdown_id')
        breakdown = get_object_or_404(OrderCostBreakdown, id=breakdown_id)

        if 'unit_price' in data:
            val = data['unit_price']
            breakdown.unit_price = Decimal(str(val).replace(',', '.')) if val not in (None, '') else 0
        if 'calculated_quantity' in data:
            val = data['calculated_quantity']
            breakdown.calculated_quantity = Decimal(str(val).replace(',', '.')) if val not in (None, '') else 0
        if 'total' in data:
            val = data['total']
            breakdown.total = Decimal(str(val).replace(',', '.')) if val not in (None, '') else 0
        else:
            breakdown.total = breakdown.calculated_quantity * breakdown.unit_price
        if 'notes' in data:
            breakdown.notes = data['notes']

        breakdown.is_manual = True
        breakdown.save()

        return JsonResponse({
            'ok': True,
            'id': breakdown.id,
            'total': str(breakdown.total),
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_update_shipping(request):
    """Actualizar costo de envío de un pedido"""
    try:
        data = json.loads(request.body)
        order_type = data.get('order_type', 'internal')
        order_id = data.get('order_id')
        val = data.get('shipping_cost', 0)
        shipping_cost = Decimal(str(val).replace(',', '.')) if val not in (None, '') else 0

        if order_type == 'internal':
            order = get_object_or_404(InternalOrder, id=order_id)
        else:
            order = get_object_or_404(Order, id=order_id)

        order.shipping_cost = shipping_cost
        order.save(update_fields=['shipping_cost'])

        return JsonResponse({'ok': True, 'shipping_cost': str(shipping_cost)})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_update_discount(request):
    """Actualizar descuento de un pedido"""
    try:
        data = json.loads(request.body)
        order_type = data.get('order_type', 'internal')
        order_id = data.get('order_id')
        val = data.get('discount_amount', 0)
        discount_amount = Decimal(str(val).replace(',', '.')) if val not in (None, '') else 0

        if order_type == 'internal':
            order = get_object_or_404(InternalOrder, id=order_id)
            order.discount_amount = discount_amount
            order.recalculate_totals()
        else:
            order = get_object_or_404(Order, id=order_id)
            order.discount_amount = discount_amount
            order.save(update_fields=['discount_amount'])

        return JsonResponse({'ok': True, 'discount_amount': str(discount_amount), 'total_estimated': str(order.total_estimated)})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


# ========================
# MEDIDAS DE VARIANTES
# ========================

@login_required
@user_passes_test(is_staff)
@require_POST
def api_update_variant_dimensions(request):
    """Actualizar medidas (alto/ancho) de una variante"""
    try:
        data = json.loads(request.body)
        variant_id = data.get('variant_id')
        variant = get_object_or_404(ProductVariant, id=variant_id)

        if 'height_cm' in data:
            val = data['height_cm']
            variant.height_cm = Decimal(str(val).replace(',', '.')) if val not in (None, '', 'null') else None
        if 'width_cm' in data:
            val = data['width_cm']
            variant.width_cm = Decimal(str(val).replace(',', '.')) if val not in (None, '', 'null') else None

        variant.save(update_fields=['height_cm', 'width_cm'])

        return JsonResponse({
            'ok': True,
            'id': variant.id,
            'height_cm': str(variant.height_cm) if variant.height_cm else None,
            'width_cm': str(variant.width_cm) if variant.width_cm else None,
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
