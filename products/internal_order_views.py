"""
Vistas para el sistema de Pedidos Internos con Drag & Drop
Compatible con PythonAnywhere - Solo Vanilla JS + Bootstrap 5
"""
import json
import random
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.db.models import F, Max, Q, Sum
from django.views.decorators.http import require_POST, require_GET
from django.core.paginator import Paginator

from .models import (
    Product, ProductVariant, Category, Material, Size, Color,
    InternalOrder, InternalOrderItem, InternalOrderGroup
)


def is_staff(user):
    """Verifica si el usuario es staff o superusuario"""
    return user.is_staff or user.is_superuser


def _latest_active_product_ids(product_type=None):
    """
    Retorna IDs de productos activos manteniendo solo el registro mas reciente
    por combinacion (name, product_type). Evita mostrar duplicados antiguos.
    """
    products = Product.objects.filter(is_active=True)
    if product_type:
        products = products.filter(product_type=product_type)

    return products.values('name', 'product_type').annotate(
        latest_id=Max('id')
    ).values_list('latest_id', flat=True)


# ============================================================
# VISTAS DE PÁGINAS
# ============================================================

@login_required
@user_passes_test(is_staff)
def internal_orders_list_view(request):
    """Lista de todos los pedidos internos"""
    orders = InternalOrder.objects.all().select_related('created_by', 'financial_status')

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

    # Garantiza estado financiero para cada fila visible (evita "Sin estado" por datos antiguos).
    from contabilidad.job_costing_services import ensure_financial_status
    for order in orders_page.object_list:
        if not hasattr(order, 'financial_status'):
            order.financial_status = ensure_financial_status(internal_order=order)

    from contabilidad.models_job_costing import FinancialStatus

    context = {
        'orders': orders_page,
        'status_choices': InternalOrder.STATUS_CHOICES,
        'current_status': status_filter,
        'search_query': search or '',
        'financial_state_choices': [
            (code, label) for code, label in FinancialStatus.STATE_CHOICES if code != 'enviado'
        ],
    }
    return render(request, 'dashboard/internal_orders/list.html', context)


@login_required
@user_passes_test(is_staff)
def internal_order_create_view(request):
    """Crea un nuevo pedido y redirige al editor"""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        initial_mode = request.POST.get('initial_mode', '')
        
        if not name:
            name = f"Pedido #{InternalOrder.objects.count() + 1}"

        description = request.POST.get('description', '')

        order = InternalOrder.objects.create(
            name=name,
            description=description,
            created_by=request.user,
            status='draft'
        )
        
        # Redireccionar con el modo si existe
        url = reverse('internal_order_edit', kwargs={'order_id': order.id})
        if initial_mode:
            url += f"?mode={initial_mode}"
            
        return redirect(url)

    return render(request, 'dashboard/internal_orders/create.html')


import csv
from django.http import HttpResponse

@login_required
@user_passes_test(is_staff)
def internal_order_export_csv_view(request, order_id):
    """Exporta el pedido a CSV"""
    order = get_object_or_404(InternalOrder, id=order_id)
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="Pedido_{order.id}_{order.created_at.strftime("%Y-%m-%d")}.csv"'
    
    # Escribir BOM para Excel
    response.write(u'\ufeff'.encode('utf8'))
    
    writer = csv.writer(response)
    # Encabezados
    writer.writerow(['Referencia', 'Cantidad', 'Tamaño', 'Color', 'Material', 'Detalles Completos'])
    
    items = order.items.select_related('variant', 'variant__size', 'variant__color', 'variant__material').all()
    
    for item in items:
        size = item.variant.size.name if item.variant and item.variant.size else ''
        color = item.variant.color.name if item.variant and item.variant.color else ''
        material = item.variant.material.name if item.variant and item.variant.material else ''
        
        writer.writerow([
            item.product_name,
            item.quantity,
            size,
            color,
            material,
            item.variant_details
        ])
            
    return response

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

    # Costos de producción
    from products.models_costs import CostType, OrderCostBreakdown
    from contabilidad.models import Account, TransactionCategory
    from decimal import Decimal
    cost_breakdowns = OrderCostBreakdown.objects.filter(
        internal_order=order
    ).select_related(
        'cost_type',
        'accounting_category',
        'accounting_transaction',
    ).order_by('-created_at')

    total_production_cost = sum(b.total for b in cost_breakdowns)
    shipping = order.shipping_cost or Decimal('0')
    grand_total_cost = total_production_cost + shipping
    # El margen es lo que queda después de gastos y envío
    margin = (order.total_estimated or Decimal('0')) - grand_total_cost

    # Estado financiero (Job Costing)
    from contabilidad.job_costing_services import ensure_financial_status
    from contabilidad.models_job_costing import FinancialStatus
    financial_status = ensure_financial_status(internal_order=order)

    context = {
        'order': order,
        'order_items': order_items,
        'cost_breakdowns': cost_breakdowns,
        'cost_types': CostType.objects.filter(is_active=True).order_by('name'),
        'accounting_accounts': Account.objects.order_by('name'),
        'accounting_categories': TransactionCategory.objects.filter(transaction_type='egreso').order_by('name'),
        'total_production_cost': total_production_cost,
        'grand_total_cost': grand_total_cost,
        'margin': margin,
        'financial_status': financial_status,
        'financial_state_choices': FinancialStatus.STATE_CHOICES,
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
            order.save(update_fields=['status'])
            from contabilidad.job_costing_services import sync_internal_order_financial_status
            sync_internal_order_financial_status(order, allow_downgrade=True)

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
    if next_url:
        return redirect(next_url)
    return redirect('internal_order_edit', order_id=order.id)


# ============================================================
# APIs AJAX
# ============================================================

@login_required
@user_passes_test(is_staff)
@require_POST
def api_internal_order_update_status(request):
    """Actualiza estado operativo por AJAX y sincroniza Job Costing."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    order_id = data.get('order_id')
    new_status = data.get('status')
    if not order_id or not new_status:
        return JsonResponse({'status': 'error', 'message': 'Parámetros faltantes'}, status=400)

    valid_statuses = [s[0] for s in InternalOrder.STATUS_CHOICES]
    if new_status not in valid_statuses:
        return JsonResponse({'status': 'error', 'message': 'Estado inválido'}, status=400)

    order = get_object_or_404(InternalOrder, id=order_id)
    if order.status != new_status:
        order.status = new_status
        order.save(update_fields=['status'])

    from contabilidad.job_costing_services import sync_internal_order_financial_status
    financial_status = sync_internal_order_financial_status(order, allow_downgrade=True)

    return JsonResponse({
        'status': 'ok',
        'order': {
            'id': order.id,
            'status': order.status,
            'status_display': order.get_status_display(),
            'status_color': order.get_status_color(),
        },
        'financial_status': {
            'id': financial_status.id,
            'state': financial_status.state,
            'state_display': financial_status.get_state_display(),
            'badge_class': financial_status.get_state_badge_class(),
        } if financial_status else None,
    })


@login_required
@require_POST
def api_get_available_filters(request):
    """
    Devuelve los filtros disponibles BASADO en el tipo de producto seleccionado.
    Solo devuelve atributos que realmente existen en variantes activas.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    product_type = data.get('product_type', '')

    # 1. Base: solo variantes de productos activos y no duplicados por nombre/tipo
    latest_product_ids = _latest_active_product_ids(product_type if product_type else None)
    variants_query = ProductVariant.objects.filter(product_id__in=latest_product_ids)

    # 2. Si hay tipo seleccionado, filtramos estrictamente
    if product_type:
        variants_query = variants_query.filter(product__product_type=product_type)

    # 3. Obtener IDs únicos de atributos que están EN USO por estas variantes
    # Esto soluciona que salgan materiales de Vinilo cuando estás en Impresos
    material_ids = variants_query.values_list('material_id', flat=True).distinct()
    size_ids = variants_query.values_list('size_id', flat=True).distinct()
    color_ids = variants_query.values_list('color_id', flat=True).distinct()
    category_ids = variants_query.values_list('product__categories__id', flat=True).distinct()

    # 4. Construir las listas de objetos basados en los IDs encontrados
    
    # Materiales
    available_materials = list(Material.objects.filter(id__in=material_ids).values('id', 'name').order_by('name'))
    
    # Tamaños
    available_sizes = list(Size.objects.filter(id__in=size_ids).values('id', 'name', 'dimensions').order_by('name'))
    
    # Colores
    available_colors = list(Color.objects.filter(id__in=color_ids).values('id', 'name', 'hex_code').order_by('name'))

    # Categorías
    available_categories = list(Category.objects.filter(id__in=category_ids).values('id', 'name').order_by('name'))

    return JsonResponse({
        'status': 'ok',
        'filters': {
            'has_materials': len(available_materials) > 0,
            'has_sizes': len(available_sizes) > 0,
            'has_colors': len(available_colors) > 0,
            'materials': available_materials,
            'sizes': available_sizes,
            'colors': available_colors,
            'categories': available_categories,
        }
    })


@login_required
@require_POST
def api_filter_variants(request):
    """
    Filtra variantes según criterios estrictos.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    product_type = data.get('product_type')
    latest_product_ids = _latest_active_product_ids(product_type if product_type else None)

    # 1. Base: Solo productos activos no duplicados (evita productos viejos repetidos)
    variants = ProductVariant.objects.select_related(
        'product', 'size', 'material', 'color'
    ).filter(product_id__in=latest_product_ids)

    # --- APLICACIÓN DE FILTROS ---

    # Tipo de Producto
    if product_type:
        variants = variants.filter(product__product_type=product_type)

    # Categoría
    category_id = data.get('category_id')
    if category_id:
        variants = variants.filter(product__categories__id=category_id)

    # Material
    material_id = data.get('material_id')
    if material_id:
        variants = variants.filter(material_id=material_id)

    # Tamaño (Aquí estaba el problema, aseguramos que el ID venga como entero si no es nulo)
    size_id = data.get('size_id')
    if size_id:
        variants = variants.filter(size_id=size_id)

    # Color
    color_id = data.get('color_id')
    if color_id:
        variants = variants.filter(color_id=color_id)

    # Búsqueda de texto
    search_query = data.get('search', '').strip()
    if search_query:
        variants = variants.filter(
            Q(product__name__icontains=search_query) |
            Q(product__description__icontains=search_query)
        )

    # Precios
    min_price = data.get('min_price')
    max_price = data.get('max_price')
    if min_price:
        variants = variants.filter(price__gte=Decimal(str(min_price)))
    if max_price:
        variants = variants.filter(price__lte=Decimal(str(max_price)))

    # Limitar y ordenar
    # Usamos distinct() para evitar duplicados si un producto tiene múltiples categorías
    variants = variants.distinct().order_by('product__name', 'size__name')
    
    # Paginación (50 items por página para mejorar rendimiento)
    page_number = data.get('page', 1)
    items_per_page = 50
    paginator = Paginator(variants, items_per_page)
    
    try:
        variants_page = paginator.page(page_number)
    except:
        variants_page = paginator.page(1)

    # Construir respuesta JSON
    items = []
    for v in variants_page:
        # Imagen segura
        image_url = ''
        if v.product.image:
            try:
                image_url = v.product.image.url
            except:
                pass
        
        # Construir texto de la variante explícitamente para depuración visual
        variant_text = f"{v.size.name if v.size else ''} - {v.material.name if v.material else ''}"
        if v.color:
            variant_text += f" - {v.color.name}"

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
            'variant_text': variant_text
        })

    return JsonResponse({
        'status': 'ok',
        'items': items,
        'count': paginator.count,
        'has_next': variants_page.has_next(),
        'has_previous': variants_page.has_previous(),
        'current_page': variants_page.number,
        'num_pages': paginator.num_pages
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
    Si allow_repeat=True y no hay suficientes, repite desde el inicio.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    order_id = data.get('order_id')
    quantity = int(data.get('quantity', 10))
    allow_repeat = data.get('allow_repeat', False)

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

    product_type = data.get('product_type')
    latest_product_ids = _latest_active_product_ids(product_type if product_type else None)

    # Construir query con filtros
    variants = ProductVariant.objects.select_related(
        'product', 'size', 'material', 'color'
    ).filter(product_id__in=latest_product_ids)

    # Aplicar filtros
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

    color_id = data.get('color_id')
    if color_id:
        variants = variants.filter(color_id=color_id)

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

    # Obtener todas las variantes disponibles (sin excluir existentes primero para repetir si es necesario)
    all_variants_list = list(variants.distinct())

    if not all_variants_list:
        return JsonResponse({
            'status': 'ok',
            'added_count': 0,
            'added_items': [],
            'message': 'No hay variantes disponibles con estos filtros',
            'order_totals': {
                'total_items': order.total_items,
                'total_estimated': float(order.total_estimated)
            }
        })

    # Excluir variantes que ya están en el pedido para la primera pasada
    existing_variant_ids = set(order.items.values_list('variant_id', flat=True))
    new_variants = [v for v in all_variants_list if v.id not in existing_variant_ids]

    # Seleccionar variantes
    selected = []

    if allow_repeat and len(new_variants) < quantity:
        # Primero agregar todas las nuevas
        selected.extend(new_variants)
        remaining = quantity - len(new_variants)

        # Si aún faltan, repetir desde el inicio de todas las variantes
        while remaining > 0:
            # Elegir aleatoriamente de todas las variantes (pueden repetirse)
            batch_size = min(remaining, len(all_variants_list))
            if batch_size == len(all_variants_list):
                selected.extend(all_variants_list)
            else:
                selected.extend(random.sample(all_variants_list, batch_size))
            remaining -= batch_size
    else:
        # Comportamiento normal: solo nuevas variantes
        if len(new_variants) > quantity:
            selected = random.sample(new_variants, quantity)
        else:
            selected = new_variants

    # Agregar al pedido
    added_items = []
    for variant in selected:
        # Verificar si ya existe este item en el pedido
        existing_item = order.items.filter(variant=variant).first()

        if existing_item:
            # Incrementar cantidad si ya existe
            existing_item.quantity += 1
            existing_item.save()

            image_url = ''
            if variant.product.image:
                try:
                    image_url = variant.product.image.url
                except:
                    pass

            added_items.append({
                'id': existing_item.id,
                'product_name': existing_item.product_name,
                'variant_details': existing_item.variant_details,
                'quantity': existing_item.quantity,
                'unit_price': float(existing_item.unit_price),
                'image_url': image_url,
            })
        else:
            # Crear nuevo item
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
                'quantity': item.quantity,
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


@login_required
@user_passes_test(is_staff)
def internal_order_tasks_view(request, order_id):
    """Vista de gestión de tareas de producción para un pedido"""
    order = get_object_or_404(InternalOrder, id=order_id)
    items = order.items.all().select_related(
        'variant__product',
        'variant__size',
        'variant__material',
        'variant__color'
    )

    context = {
        'order': order,
        'order_items': items,
    }
    return render(request, 'dashboard/internal_orders/tasks.html', context)


@login_required
@require_POST
def api_internal_order_update_task(request):
    """Actualiza el progreso de una referencia (tarea)"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    item_id = data.get('item_id')
    completed_qty = data.get('completed_quantity')

    if not item_id or completed_qty is None:
        return JsonResponse({
            'status': 'error',
            'message': 'Faltan parámetros'
        }, status=400)

    item = get_object_or_404(InternalOrderItem, id=item_id)
    
    try:
        completed_qty = int(completed_qty)
        if completed_qty < 0:
            completed_qty = 0
        if completed_qty > item.quantity:
            completed_qty = item.quantity
    except ValueError:
        return JsonResponse({
            'status': 'error',
            'message': 'Cantidad inválida'
        }, status=400)

    item.completed_quantity = completed_qty
    item.save()

    return JsonResponse({
        'status': 'ok',
        'item': {
            'id': item.id,
            'completed_quantity': item.completed_quantity,
            'is_completed': item.completed_quantity >= item.quantity
        }
    })
