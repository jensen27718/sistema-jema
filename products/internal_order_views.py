"""
Vistas para el sistema de Pedidos Internos con Drag & Drop
Compatible con PythonAnywhere - Solo Vanilla JS + Bootstrap 5
"""
import json
import random
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.db.models import Q, Sum, F
from django.views.decorators.http import require_POST, require_GET
from django.core.paginator import Paginator

from .models import (
    Product, ProductVariant, Category, Material, Size, Color,
    InternalOrder, InternalOrderItem, InternalOrderGroup
)


def is_staff(user):
    """Verifica si el usuario es staff o superusuario"""
    return user.is_staff or user.is_superuser


# ============================================================
# VISTAS DE PÁGINAS
# ============================================================

@login_required
@user_passes_test(is_staff)
def internal_orders_list_view(request):
    """Lista de todos los pedidos internos"""
    orders = InternalOrder.objects.all().select_related('created_by')

    # Filtro por estado
    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(status=status_filter)

    # Búsqueda
    search = request.GET.get('q')
    if search:
        orders = orders.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search)
        )

    # Paginación
    paginator = Paginator(orders, 20)
    page = request.GET.get('page', 1)
    orders_page = paginator.get_page(page)

    context = {
        'orders': orders_page,
        'status_choices': InternalOrder.STATUS_CHOICES,
        'current_status': status_filter,
        'search_query': search or '',
    }
    return render(request, 'dashboard/internal_orders/list.html', context)


@login_required
@user_passes_test(is_staff)
def internal_order_create_view(request):
    """Crea un nuevo pedido y redirige al editor"""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            name = f"Pedido #{InternalOrder.objects.count() + 1}"

        description = request.POST.get('description', '')

        order = InternalOrder.objects.create(
            name=name,
            description=description,
            created_by=request.user,
            status='draft'
        )
        return redirect('internal_order_edit', order_id=order.id)

    return render(request, 'dashboard/internal_orders/create.html')


@login_required
@user_passes_test(is_staff)
def internal_order_edit_view(request, order_id):
    """Editor principal con drag & drop"""
    order = get_object_or_404(InternalOrder, id=order_id)

    # Datos para los filtros
    product_types = Product.TYPE_CHOICES
    categories = Category.objects.all().order_by('name')
    materials = Material.objects.all().order_by('name')
    sizes = Size.objects.all().order_by('name')
    colors = Color.objects.all().order_by('name')

    # Items actuales del pedido
    order_items = order.items.all().select_related(
        'variant__product',
        'variant__size',
        'variant__material',
        'variant__color'
    )

    context = {
        'order': order,
        'order_items': order_items,
        'product_types': product_types,
        'categories': categories,
        'materials': materials,
        'sizes': sizes,
        'colors': colors,
    }
    return render(request, 'dashboard/internal_orders/editor.html', context)


@login_required
@user_passes_test(is_staff)
def internal_order_detail_view(request, order_id):
    """Vista de detalle de un pedido (solo lectura)"""
    order = get_object_or_404(InternalOrder, id=order_id)

    order_items = order.items.all().select_related(
        'variant__product',
        'variant__size',
        'variant__material',
        'variant__color'
    )

    context = {
        'order': order,
        'order_items': order_items,
    }
    return render(request, 'dashboard/internal_orders/detail.html', context)


@login_required
@user_passes_test(is_staff)
def internal_order_delete_view(request, order_id):
    """Elimina un pedido interno"""
    order = get_object_or_404(InternalOrder, id=order_id)

    if request.method == 'POST':
        order.delete()
        return redirect('internal_orders_list')

    context = {'order': order}
    return render(request, 'dashboard/internal_orders/delete.html', context)


@login_required
@user_passes_test(is_staff)
def internal_order_confirm_view(request, order_id):
    """Confirma un pedido (cambia estado a confirmado)"""
    order = get_object_or_404(InternalOrder, id=order_id)

    if request.method == 'POST':
        if order.status == 'draft':
            order.status = 'confirmed'
            order.save()

    return redirect('internal_order_edit', order_id=order.id)


@login_required
@user_passes_test(is_staff)
def internal_order_update_status_view(request, order_id):
    """Actualiza el estado de un pedido"""
    order = get_object_or_404(InternalOrder, id=order_id)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        valid_statuses = [s[0] for s in InternalOrder.STATUS_CHOICES]

        if new_status in valid_statuses:
            order.status = new_status
            order.save()

    return redirect('internal_order_edit', order_id=order.id)


# ============================================================
# APIs AJAX
# ============================================================

@login_required
@require_POST
def api_filter_variants(request):
    """
    Filtra variantes según criterios.
    Retorna JSON con lista de variantes.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    variants = ProductVariant.objects.select_related(
        'product', 'size', 'material', 'color'
    ).filter(product__is_online=True)

    # Búsqueda por nombre/referencia y descripción
    search_query = data.get('search', '').strip()
    if search_query:
        variants = variants.filter(
            Q(product__name__icontains=search_query) |
            Q(product__description__icontains=search_query)
        )

    # Filtro por tipo de producto
    product_type = data.get('product_type')
    if product_type:
        variants = variants.filter(product__product_type=product_type)

    # Filtro por categoría
    category_id = data.get('category_id')
    if category_id:
        variants = variants.filter(product__categories__id=category_id)

    # Filtro por material (puede ser uno o varios)
    material_id = data.get('material_id')
    material_ids = data.get('material_ids', [])
    if material_id:
        variants = variants.filter(material_id=material_id)
    elif material_ids:
        variants = variants.filter(material_id__in=material_ids)

    # Filtro por tamaño
    size_id = data.get('size_id')
    if size_id:
        variants = variants.filter(size_id=size_id)

    # Filtro por color
    color_id = data.get('color_id')
    if color_id:
        variants = variants.filter(color_id=color_id)

    # Filtro por rango de precio
    min_price = data.get('min_price')
    max_price = data.get('max_price')
    if min_price:
        try:
            variants = variants.filter(price__gte=Decimal(str(min_price)))
        except:
            pass
    if max_price:
        try:
            variants = variants.filter(price__lte=Decimal(str(max_price)))
        except:
            pass

    # Limitar resultados para rendimiento
    variants = variants.distinct().order_by('product__name')[:150]

    # Construir respuesta
    items = []
    for v in variants:
        image_url = ''
        if v.product.image:
            try:
                image_url = v.product.image.url
            except:
                pass

        items.append({
            'id': v.id,
            'product_id': v.product.id,
            'product_name': v.product.name,
            'product_image': image_url,
            'size': v.size.name if v.size else '',
            'size_dimensions': v.size.dimensions if v.size else '',
            'material': v.material.name if v.material else '',
            'color': v.color.name if v.color else '',
            'color_hex': v.color.hex_code if v.color else '#cccccc',
            'price': float(v.price) if v.price else 0,
            'variant_text': _build_variant_text(v)
        })

    return JsonResponse({
        'status': 'ok',
        'items': items,
        'count': len(items)
    })


@login_required
@require_POST
def api_internal_order_add_item(request):
    """Agrega un item al pedido (usado por drag & drop)"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    order_id = data.get('order_id')
    variant_id = data.get('variant_id')
    quantity = int(data.get('quantity', 1))

    if not order_id or not variant_id:
        return JsonResponse({
            'status': 'error',
            'message': 'Faltan parámetros requeridos'
        }, status=400)

    order = get_object_or_404(InternalOrder, id=order_id)
    variant = get_object_or_404(ProductVariant, id=variant_id)

    # Verificar si ya existe este item en el pedido
    existing_item = order.items.filter(variant=variant).first()

    if existing_item:
        # Sumar cantidad
        existing_item.quantity += quantity
        existing_item.save()
        item = existing_item
        is_new = False
    else:
        # Crear nuevo item con snapshot
        item = InternalOrderItem.objects.create(
            order=order,
            variant=variant,
            quantity=quantity,
            product_name=variant.product.name,
            variant_details=_build_variant_text(variant),
            unit_price=variant.price or 0
        )
        is_new = True

    # Recalcular totales
    order.recalculate_totals()

    # Obtener imagen
    image_url = ''
    if variant.product.image:
        try:
            image_url = variant.product.image.url
        except:
            pass

    return JsonResponse({
        'status': 'ok',
        'is_new': is_new,
        'item': {
            'id': item.id,
            'product_name': item.product_name,
            'variant_details': item.variant_details,
            'quantity': item.quantity,
            'unit_price': float(item.unit_price),
            'subtotal': float(item.get_subtotal()),
            'image_url': image_url,
        },
        'order_totals': {
            'total_items': order.total_items,
            'total_estimated': float(order.total_estimated)
        }
    })


@login_required
@require_POST
def api_internal_order_remove_item(request):
    """Elimina un item del pedido"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    item_id = data.get('item_id')

    if not item_id:
        return JsonResponse({
            'status': 'error',
            'message': 'Falta item_id'
        }, status=400)

    item = get_object_or_404(InternalOrderItem, id=item_id)
    order = item.order

    item.delete()

    # Recalcular totales
    order.recalculate_totals()

    return JsonResponse({
        'status': 'ok',
        'order_totals': {
            'total_items': order.total_items,
            'total_estimated': float(order.total_estimated)
        }
    })


@login_required
@require_POST
def api_internal_order_update_qty(request):
    """Actualiza la cantidad de un item"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    item_id = data.get('item_id')
    quantity = data.get('quantity')

    if not item_id or quantity is None:
        return JsonResponse({
            'status': 'error',
            'message': 'Faltan parámetros'
        }, status=400)

    try:
        quantity = int(quantity)
        if quantity < 1:
            quantity = 1
    except ValueError:
        return JsonResponse({
            'status': 'error',
            'message': 'Cantidad inválida'
        }, status=400)

    item = get_object_or_404(InternalOrderItem, id=item_id)
    item.quantity = quantity
    item.save()

    order = item.order
    order.recalculate_totals()

    return JsonResponse({
        'status': 'ok',
        'item': {
            'id': item.id,
            'quantity': item.quantity,
            'subtotal': float(item.get_subtotal())
        },
        'order_totals': {
            'total_items': order.total_items,
            'total_estimated': float(order.total_estimated)
        }
    })


@login_required
@require_POST
def api_internal_order_auto_select(request):
    """
    Selección semi-automática de referencias.
    Selecciona aleatoriamente N variantes según los filtros.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    order_id = data.get('order_id')
    quantity = int(data.get('quantity', 10))

    if quantity > 100:
        quantity = 100
    if quantity < 1:
        quantity = 1

    if not order_id:
        return JsonResponse({
            'status': 'error',
            'message': 'Falta order_id'
        }, status=400)

    order = get_object_or_404(InternalOrder, id=order_id)

    # Construir query con filtros
    variants = ProductVariant.objects.select_related(
        'product', 'size', 'material', 'color'
    ).filter(product__is_online=True)

    # Aplicar filtros
    product_type = data.get('product_type')
    if product_type:
        variants = variants.filter(product__product_type=product_type)

    category_id = data.get('category_id')
    if category_id:
        variants = variants.filter(product__categories__id=category_id)

    material_ids = data.get('material_ids', [])
    material_id = data.get('material_id')
    if material_id:
        variants = variants.filter(material_id=material_id)
    elif material_ids:
        variants = variants.filter(material_id__in=material_ids)

    size_id = data.get('size_id')
    if size_id:
        variants = variants.filter(size_id=size_id)

    min_price = data.get('min_price')
    max_price = data.get('max_price')
    if min_price:
        try:
            variants = variants.filter(price__gte=Decimal(str(min_price)))
        except:
            pass
    if max_price:
        try:
            variants = variants.filter(price__lte=Decimal(str(max_price)))
        except:
            pass

    # Excluir variantes que ya están en el pedido
    existing_variant_ids = list(order.items.values_list('variant_id', flat=True))
    variants = variants.exclude(id__in=existing_variant_ids)

    # Obtener todas las variantes y seleccionar aleatoriamente
    variants_list = list(variants.distinct())

    if len(variants_list) > quantity:
        selected = random.sample(variants_list, quantity)
    else:
        selected = variants_list

    # Agregar al pedido
    added_items = []
    for variant in selected:
        item = InternalOrderItem.objects.create(
            order=order,
            variant=variant,
            quantity=1,
            product_name=variant.product.name,
            variant_details=_build_variant_text(variant),
            unit_price=variant.price or 0
        )

        image_url = ''
        if variant.product.image:
            try:
                image_url = variant.product.image.url
            except:
                pass

        added_items.append({
            'id': item.id,
            'product_name': item.product_name,
            'variant_details': item.variant_details,
            'unit_price': float(item.unit_price),
            'image_url': image_url,
        })

    # Recalcular totales
    order.recalculate_totals()

    return JsonResponse({
        'status': 'ok',
        'added_count': len(added_items),
        'added_items': added_items,
        'order_totals': {
            'total_items': order.total_items,
            'total_estimated': float(order.total_estimated)
        }
    })


@login_required
@require_POST
def api_internal_order_clear(request):
    """Elimina todos los items de un pedido"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    order_id = data.get('order_id')

    if not order_id:
        return JsonResponse({
            'status': 'error',
            'message': 'Falta order_id'
        }, status=400)

    order = get_object_or_404(InternalOrder, id=order_id)

    # Eliminar todos los items
    deleted_count = order.items.count()
    order.items.all().delete()

    # Recalcular totales (serán 0)
    order.recalculate_totals()

    return JsonResponse({
        'status': 'ok',
        'deleted_count': deleted_count,
        'order_totals': {
            'total_items': 0,
            'total_estimated': 0
        }
    })


@login_required
@require_POST
def api_internal_order_update_info(request):
    """Actualiza nombre y descripción del pedido"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    order_id = data.get('order_id')
    name = data.get('name', '').strip()
    description = data.get('description', '')

    if not order_id:
        return JsonResponse({
            'status': 'error',
            'message': 'Falta order_id'
        }, status=400)

    order = get_object_or_404(InternalOrder, id=order_id)

    if name:
        order.name = name
    order.description = description
    order.save()

    return JsonResponse({
        'status': 'ok',
        'order': {
            'id': order.id,
            'name': order.name,
            'description': order.description
        }
    })


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def _build_variant_text(variant):
    """Construye el texto descriptivo de una variante"""
    parts = []

    if variant.size:
        parts.append(variant.size.name)
    if variant.material:
        parts.append(variant.material.name)
    if variant.color:
        parts.append(variant.color.name)

    return " - ".join(parts) if parts else "Sin especificar"
