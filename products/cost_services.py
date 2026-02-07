"""
Servicio de cálculo de costos de producción por pedido.
"""
from decimal import Decimal
from math import ceil, floor
from collections import defaultdict

from products.models_costs import CostType, ProductTypeCostConfig, OrderCostBreakdown


def calculate_order_costs(order, order_type='internal'):
    """
    Calcula los costos de producción para un pedido.

    Args:
        order: InternalOrder o Order instance
        order_type: 'internal' o 'catalog'

    Returns:
        dict con resumen de costos calculados
    """
    # 1. Obtener items del pedido
    items = order.items.select_related('variant__product', 'variant__size', 'variant__material').all()

    # 2. Agrupar items por product_type
    items_by_type = defaultdict(list)
    for item in items:
        if item.variant and item.variant.product:
            ptype = item.variant.product.product_type
            items_by_type[ptype].append(item)

    # 3. Borrar breakdowns anteriores (recalcular)
    if order_type == 'internal':
        OrderCostBreakdown.objects.filter(internal_order=order).exclude(is_manual=True).delete()
    else:
        OrderCostBreakdown.objects.filter(order=order).exclude(is_manual=True).delete()

    breakdowns_created = []

    # 4. Para cada product_type, buscar configs y calcular
    for ptype, type_items in items_by_type.items():
        configs = ProductTypeCostConfig.objects.filter(
            product_type=ptype,
            cost_type__is_active=True
        ).select_related('cost_type').order_by('position')

        for config in configs:
            results = _calculate_cost(config, type_items)
            for result in results:
                breakdown_kwargs = {
                    'cost_type': config.cost_type,
                    'product_type': ptype,
                    'description': result['description'],
                    'calculated_quantity': result['quantity'],
                    'unit_price': result['unit_price'],
                    'total': result['total'],
                    'is_manual': False,
                }

                if order_type == 'internal':
                    breakdown_kwargs['internal_order'] = order
                else:
                    breakdown_kwargs['order'] = order

                breakdown = OrderCostBreakdown.objects.create(**breakdown_kwargs)
                breakdowns_created.append(breakdown)

    # 5. Calcular totales
    total_costs = sum(b.total for b in breakdowns_created)

    # Incluir costos manuales existentes
    if order_type == 'internal':
        manual_costs = OrderCostBreakdown.objects.filter(
            internal_order=order, is_manual=True
        ).values_list('total', flat=True)
    else:
        manual_costs = OrderCostBreakdown.objects.filter(
            order=order, is_manual=True
        ).values_list('total', flat=True)

    total_manual = sum(manual_costs)
    shipping = order.shipping_cost or Decimal('0')

    return {
        'breakdowns': breakdowns_created,
        'total_production': total_costs,
        'total_manual': total_manual,
        'shipping': shipping,
        'grand_total': total_costs + total_manual + shipping,
    }


def _calculate_cost(config, items):
    """
    Calcula un costo específico según el método de cálculo.
    Separa items por material normal vs especial si hay precio especial configurado.

    Returns:
        list of dicts con description, quantity, unit_price, total
    """
    method = config.calculation_method
    cost_type = config.cost_type
    normal_price = cost_type.default_unit_price
    special_price = cost_type.special_material_price

    # Si hay precio especial, separar items por tipo de material
    has_special_pricing = special_price and special_price > 0

    if has_special_pricing and method in ('linear_meters', 'per_unit'):
        normal_items = [i for i in items if not (i.variant and i.variant.material and i.variant.material.is_special)]
        special_items = [i for i in items if i.variant and i.variant.material and i.variant.material.is_special]

        results = []
        if normal_items:
            r = _calc_single(method, cost_type, normal_items, normal_price, config.material_width_cm, "")
            if r:
                results.append(r)
        if special_items:
            mat_name = special_items[0].variant.material.name if special_items[0].variant.material else "Especial"
            r = _calc_single(method, cost_type, special_items, special_price, config.material_width_cm, f" ({mat_name})")
            if r:
                results.append(r)
        return results
    else:
        r = _calc_single(method, cost_type, items, normal_price, config.material_width_cm, "")
        return [r] if r else []


def _calc_single(method, cost_type, items, unit_price, material_width_cm, suffix):
    """Calcula un solo grupo de items con un precio dado"""
    if method == 'per_unit':
        r = _calc_per_unit(cost_type, items, unit_price)
    elif method == 'linear_meters':
        r = _calc_linear_meters(cost_type, items, unit_price, material_width_cm)
    elif method == 'square_meters':
        r = _calc_square_meters(cost_type, items, unit_price)
    elif method == 'manual':
        r = _calc_manual(cost_type)
    else:
        return None

    if r and suffix:
        r['description'] = r['description'] + suffix
    return r


def _calc_per_unit(cost_type, items, unit_price):
    """Per unit: total_units × unit_price"""
    total_units = sum(item.quantity for item in items)
    if total_units == 0:
        return None

    total = Decimal(str(total_units)) * unit_price
    return {
        'description': f"{cost_type.name} - {total_units} unidades",
        'quantity': Decimal(str(total_units)),
        'unit_price': unit_price,
        'total': total,
    }


def _calc_linear_meters(cost_type, items, unit_price, material_width_cm):
    """
    Linear meters: layout items on material roll.
    Groups items by (height_cm, width_cm), calculates how many columns fit
    on the material width, then how many rows needed.
    """
    if not material_width_cm or material_width_cm <= 0:
        return None

    # Agrupar items por dimensiones de variante
    groups = defaultdict(lambda: Decimal('0'))
    for item in items:
        v = item.variant
        if v and v.height_cm and v.width_cm:
            key = (v.height_cm, v.width_cm)
            groups[key] += Decimal(str(item.quantity))

    if not groups:
        return None

    total_linear_cm = Decimal('0')
    material_w = Decimal(str(material_width_cm))

    for (height_cm, width_cm), qty in groups.items():
        columns = int(material_w // width_cm)
        if columns < 1:
            columns = 1
        rows = ceil(int(qty) / columns)
        linear_cm = Decimal(str(rows)) * height_cm
        total_linear_cm += linear_cm

    total_linear_meters = total_linear_cm / Decimal('100')
    total = total_linear_meters * unit_price

    return {
        'description': f"{cost_type.name} - {total_linear_meters:.2f} metros lineales",
        'quantity': total_linear_meters,
        'unit_price': unit_price,
        'total': total,
    }


def _calc_square_meters(cost_type, items, unit_price):
    """Square meters: sum of (height × width × quantity) for each item"""
    total_area_cm2 = Decimal('0')

    for item in items:
        v = item.variant
        if v and v.height_cm and v.width_cm:
            area = v.height_cm * v.width_cm * Decimal(str(item.quantity))
            total_area_cm2 += area

    if total_area_cm2 == 0:
        return None

    total_m2 = total_area_cm2 / Decimal('10000')
    total = total_m2 * unit_price

    return {
        'description': f"{cost_type.name} - {total_m2:.4f} m²",
        'quantity': total_m2,
        'unit_price': unit_price,
        'total': total,
    }


def _calc_manual(cost_type):
    """Manual: creates a placeholder with 0 cost for admin to fill in"""
    return {
        'description': f"{cost_type.name} - (pendiente de ingreso manual)",
        'quantity': Decimal('0'),
        'unit_price': cost_type.default_unit_price,
        'total': Decimal('0'),
    }
