from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
# Importa TANTO Product COMO Category
from .models import Product, Category, ProductVariant,Cart, CartItem
from .forms import ProductForm, CategoryForm
from .services import generar_variantes_vinilo, generar_variantes_impresos # <--- Importamos la magia
from django.db.models import Min, Q
import json  # <--- AGREGAR ESTA LÍNEA
from django.http import JsonResponse
from django.core.serializers import serialize
from django.core.serializers.json import DjangoJSONEncoder
from django.core.paginator import Paginator

import urllib.parse # <--- AGREGAR ARRIBA
from .models import ShippingAddress, Order, OrderItem, OrderStatus # <--- IMPORTAR NUEVOS MODELOS
from .models import BulkUploadBatch, BulkUploadItem  # Bulk upload models
from .forms import AddressForm # <--- IMPORTAR FORM
from .bulk_forms import BulkUploadForm, MassEditForm  # Bulk upload forms
# NO Celery - Todo síncrono para PythonAnywhere

# ... (Tus otras vistas) ...

@login_required
def checkout_process_view(request):
    # 1. Verificar si el carrito tiene items
    cart, _ = Cart.objects.get_or_create(user=request.user)
    if cart.items.count() == 0:
        return redirect('cart_view')

    # 2. Verificar si el usuario ya tiene dirección
    last_address = ShippingAddress.objects.filter(user=request.user).last()

    if not last_address:
        # Si no tiene, redirigir a crear dirección
        return redirect('address_create')
    
    # 3. Si tiene dirección, CREAR PEDIDO
    default_status = OrderStatus.objects.filter(is_default=True).first() # Obtener estado por defecto
    
    order = Order.objects.create(
        user=request.user,
        address=last_address,
        total=cart.get_total(),
        status=default_status # Asignar estado
    )

    # Mover items del carrito al pedido (Snapshot)
    items_text = ""
    for item in cart.items.all():
        variant_desc = f"{item.variant.size.name}"
        if item.variant.color:
            variant_desc += f" - {item.variant.color.name}"
        
        OrderItem.objects.create(
            order=order,
            product=item.variant.product, # <--- GUARDAMOS LA REFERENCIA
            product_name=item.variant.product.name,
            variant_text=variant_desc,
            quantity=item.quantity,
            price=item.variant.price
        )
        # Formato para WhatsApp: "- 2x Referencia (Detalle)"
        items_text += f"- {item.quantity}x {item.variant.product.name} ({variant_desc})\n"

    # Vaciar carrito
    cart.items.all().delete()

    # 4. Generar Link de WhatsApp
    # Formatear precio con punto de mil (truco python simple)
    total_fmt = "{:,.0f}".format(order.total).replace(",", ".")
    
    # URL para ver el pedido en la web (usamos request.build_absolute_uri)
    order_url = request.build_absolute_uri(reverse('order_detail', args=[order.id]))

    message = (
        f"Hola JEMA! 👋 Acabo de hacer un pedido.\n\n"
        f"👤 *Cliente:* {last_address.full_name}\n"
        f"📍 *Dirección:* {last_address.city}, {last_address.address_line} ({last_address.neighborhood})\n"
        f"📞 *Tel:* {last_address.phone}\n\n"
        f"📦 *PEDIDO #{order.id}:*\n"
        f"{items_text}\n"
        f"💰 *TOTAL: ${total_fmt}*\n\n"
        f"Ver detalle completo aquí:\n{order_url}"
    )
    
    whatsapp_url = f"https://wa.me/573212165252?text={urllib.parse.quote(message)}"

    return redirect(whatsapp_url)

@login_required
def address_create_view(request):
    if request.method == 'POST':
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            return redirect('checkout_process') # Volver al proceso para crear el pedido
    else:
        form = AddressForm()
    
    return render(request, 'address_form.html', {'form': form})

@login_required
def order_detail_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    # Seguridad básica: Solo el dueño o el admin pueden verlo
    if order.user != request.user and not request.user.is_staff:
        return redirect('home')
        
    return render(request, 'order_detail.html', {'order': order})



def is_staff(user):
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(is_staff)
def product_list_view(request):
    products = Product.objects.all().order_by('-created_at')
    return render(request, 'dashboard/products/list.html', {'products': products})

@login_required
@user_passes_test(is_staff)
def product_create_view(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save()
            
            count = 0
            # --- LÓGICA DE SELECCIÓN DE PRECIOS ---
            try:
                if product.product_type == 'vinilo_corte':
                    count = generar_variantes_vinilo(product)
                
                elif product.product_type == 'impreso_globo':
                    count = generar_variantes_impresos(product) # <--- NUEVA LÍNEA
                
                if count > 0:
                    messages.success(request, f"Producto creado. Se generaron {count} precios automáticamente.")
                else:
                    messages.warning(request, "Producto creado, pero no se generaron precios (revisa los tamaños).")

            except Exception as e:
                messages.warning(request, f"Error generando precios: {e}")
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'ok', 'redirect_url': reverse('panel_product_list')})
            return redirect('panel_product_list')
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            # Devolver errores en JSON
            return JsonResponse({'status': 'error', 'errors': form.errors.as_json()}, status=400)
            
    else:
        form = ProductForm()
    
    return render(request, 'dashboard/products/form.html', {'form': form, 'title': 'Nuevo Producto'})



@login_required
@user_passes_test(is_staff)
def category_list_view(request):
    categories = Category.objects.all()
    return render(request, 'dashboard/categories/list.html', {'categories': categories})

@login_required
@user_passes_test(is_staff)
def category_create_view(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('panel_category_list')
    else:
        form = CategoryForm()
    
    return render(request, 'dashboard/categories/form.html', {'form': form, 'title': 'Nueva Categoría'})

@login_required
@user_passes_test(is_staff)
def category_update_view(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            return redirect('panel_category_list')
    else:
        form = CategoryForm(instance=category)
    
    return render(request, 'dashboard/categories/form.html', {'form': form, 'title': 'Editar Categoría'})

@login_required
@user_passes_test(is_staff)
def category_delete_view(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    if request.method == 'POST':
        category.delete()
        return redirect('panel_category_list')
    
    return render(request, 'dashboard/categories/confirm_delete.html', {'object': category})


from django.core.paginator import Paginator

def catalogo_redirect_view(request):
    """Redirige /catalogo/ al tipo por defecto (Impresos para Globos)"""
    return redirect('catalogo', type_slug='impresos-para-globos')

def catalogo_publico_view(request, type_slug, category_slug=None):
    # Mapa de slugs a códigos de BD
    TYPE_MAP = {
        'vinilos-de-corte': 'vinilo_corte',
        'impresos-para-globos': 'impreso_globo',
        'cintas-ramos': 'cinta',
        'stickers-logo': 'logo',
    }
    
    # Inverso para la UI
    SLUG_MAP = {v: k for k, v in TYPE_MAP.items()}

    current_type_code = TYPE_MAP.get(type_slug)
    if not current_type_code:
        # Si el slug no es válido, 404 o redirigir al default
        return redirect('catalogo_root')

    # 1. Obtener productos base (solo del tipo actual y online)
    products_query = Product.objects.filter(
        product_type=current_type_code,
        variants__isnull=False,
        is_online=True
    ).distinct().order_by('-created_at')

    # 2. Filtrar por categoría si existe
    current_category = None
    if category_slug:
        current_category = get_object_or_404(Category, slug=category_slug)
        products_query = products_query.filter(categories=current_category)

    # 3. Paginación
    paginator = Paginator(products_query, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # 4. Obtener categorías QUE TENGAN productos de este tipo
    # Para optimizar, podríamos filtrar solo las categorías que tienen al menos un producto activo de este tipo
    categories = []
    if not request.headers.get('x-requested-with') == 'XMLHttpRequest':
        categories = Category.objects.filter(
            products__product_type=current_type_code,
            products__is_online=True
        ).distinct()

    # 5. Construir JSON de variantes
    variants_data = {}
    products_list = []
    for product in page_obj:
        p_variants = product.variants.all()
        variants_data[product.id] = []
        for v in p_variants:
            variants_data[product.id].append({
                'id': v.id,
                'size_id': v.size.id,
                'size_name': v.size.name,
                'material_id': v.material.id,
                'color_name': v.color.name if v.color else "Estándar",
                'material_name': v.material.name,
                'color_id': v.color.id if v.color else None,
                'price': float(v.price),
                'stock': v.stock
            })
        
        products_list.append({
            'id': product.id,
            'name': product.name,
            'description': product.description or "",
            'image_url': product.image.url if product.image else None,
        })

    # 6. Respuesta AJAX
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'products': products_list,
            'variants': variants_data,
            'has_next': page_obj.has_next(),
            'next_page': page_obj.next_page_number() if page_obj.has_next() else None
        })

    # Lista de tipos disponibles para el menú
    product_types_menu = [
        {'slug': 'impresos-para-globos', 'name': 'Impresos para Globos', 'active': type_slug == 'impresos-para-globos'},
        {'slug': 'vinilos-de-corte', 'name': 'Vinilos de Corte', 'active': type_slug == 'vinilos-de-corte'},
        {'slug': 'cintas-ramos', 'name': 'Cintas para Ramos', 'active': type_slug == 'cintas-ramos'},
        {'slug': 'stickers-logo', 'name': 'Stickers Logo', 'active': type_slug == 'stickers-logo'},
    ]

    context = {
        'products': page_obj,
        'categories': categories,
        'current_category': current_category,
        'current_type_slug': type_slug,
        'product_types_menu': product_types_menu,
        'variants_json': json.dumps(variants_data, cls=DjangoJSONEncoder),
        'has_next': page_obj.has_next(),
        'next_page': page_obj.next_page_number() if page_obj.has_next() else None
    }
    return render(request, 'catalogo_tiktok.html', context)

# --- 3. VISTAS DE ESTADOS DE PEDIDO (CRUD) ---
@login_required
@user_passes_test(is_staff)
def status_list_view(request):
    statuses = OrderStatus.objects.all()
    return render(request, 'dashboard/statuses/list.html', {'statuses': statuses})

@login_required
@user_passes_test(is_staff)
def status_create_view(request):
    # Usaremos un form manual o genérico por brevedad
    if request.method == 'POST':
        name = request.POST.get('name')
        color = request.POST.get('color')
        is_default = request.POST.get('is_default') == 'on'
        
        if is_default:
            # Quitamos el default de otros
            OrderStatus.objects.update(is_default=False)
            
        OrderStatus.objects.create(name=name, color=color, is_default=is_default)
        messages.success(request, "Estado creado correctamente.")
        return redirect('panel_status_list')
        
    return render(request, 'dashboard/statuses/form.html', {'title': 'Nuevo Estado'})

@login_required
@user_passes_test(is_staff)
def status_update_view(request, status_id):
    state = get_object_or_404(OrderStatus, id=status_id)
    if request.method == 'POST':
        state.name = request.POST.get('name')
        state.color = request.POST.get('color')
        is_default = request.POST.get('is_default') == 'on'
        
        if is_default:
            OrderStatus.objects.exclude(id=state.id).update(is_default=False)
        
        state.is_default = is_default
        state.save()
        messages.success(request, "Estado actualizado.")
        return redirect('panel_status_list')
    
    return render(request, 'dashboard/statuses/form.html', {'object': state, 'title': 'Editar Estado'})

@login_required
@user_passes_test(is_staff)
def status_delete_view(request, status_id):
    state = get_object_or_404(OrderStatus, id=status_id)
    if request.method == 'POST':
        try:
            state.delete()
            messages.success(request, "Estado eliminado.")
        except:
            messages.error(request, "No se puede eliminar este estado porque hay pedidos usándolo.")
        return redirect('panel_status_list')
    # Reusamos confirmación de categorías
    return render(request, 'dashboard/categories/confirm_delete.html', {'object': state})


# --- 4. VISTAS DE GESTIÓN DE PEDIDOS ---
@login_required
@user_passes_test(is_staff)
def panel_orders_list_view(request):
    # Filtros básicos
    status_id = request.GET.get('status')
    orders = Order.objects.all().select_related('status', 'user').order_by('-created_at')
    
    if status_id:
        orders = orders.filter(status_id=status_id)
        
    statuses = OrderStatus.objects.all()
    
    return render(request, 'dashboard/orders/list.html', {
        'orders': orders, 
        'statuses': statuses,
        'current_status': int(status_id) if status_id else None
    })

@login_required
@user_passes_test(is_staff)
def panel_order_detail_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    statuses = OrderStatus.objects.all()
    
    if request.method == 'POST':
        new_status_id = request.POST.get('status_id')
        if new_status_id:
            order.status_id = new_status_id
            order.save()
            messages.success(request, f"Estado actualizado a {order.status.name}")
            return redirect('panel_order_detail', order_id=order.id)
            
    return render(request, 'dashboard/orders/detail.html', {'order': order, 'statuses': statuses})


# --- 5. VISTAS DE GESTIÓN DE CARRITOS (ADMIN) ---
@login_required
@user_passes_test(is_staff)
def panel_cart_list_view(request):
    """
    Lista todos los carritos que tienen al menos un producto.
    Esto permite ver qué clientes tienen intención de compra.
    """
    # Filtramos carritos que tengan items
    carts = Cart.objects.filter(items__isnull=False).distinct().select_related('user').order_by('-created_at')
    
    return render(request, 'dashboard/carts/list.html', {
        'carts': carts
    })

@login_required
@user_passes_test(is_staff)
def panel_cart_detail_view(request, cart_id):
    """
    Muestra el detalle de los productos en el carrito de un cliente específico.
    """
    cart = get_object_or_404(Cart, id=cart_id)
    return render(request, 'dashboard/carts/detail.html', {'cart': cart})


# --- FIN NUEVAS VISTAS ---

# --- API PARA EL CARRITO (AJAX) ---
@login_required
def add_to_cart_api(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        variant_id = data.get('variant_id')
        quantity = int(data.get('quantity', 1))

        cart, _ = Cart.objects.get_or_create(user=request.user)
        variant = get_object_or_404(ProductVariant, id=variant_id)

        item, created = CartItem.objects.get_or_create(cart=cart, variant=variant)
        if not created:
            item.quantity += quantity
        else:
            item.quantity = quantity
        item.save()

        return JsonResponse({'status': 'ok', 'total_items': cart.items.count()})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
@user_passes_test(is_staff)
def product_update_view(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'ok', 'redirect_url': reverse('panel_product_list')})
            return redirect('panel_product_list')
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'errors': form.errors.as_json()}, status=400)
    else:
        form = ProductForm(instance=product)
    return render(request, 'dashboard/products/form.html', {'form': form, 'title': 'Editar Producto'})

@login_required
@user_passes_test(is_staff)
def product_delete_view(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        product.delete()
        return redirect('panel_product_list')
    # Reusamos la plantilla de borrar categorías para no crear otra
    return render(request, 'dashboard/categories/confirm_delete.html', {'object': product})

@login_required
@user_passes_test(is_staff)
def product_variants_view(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    variants = product.variants.all().order_by('price')
    return render(request, 'dashboard/products/variants.html', {'product': product, 'variants': variants})


# ... imports anteriores ...

# --- VISTA DE LA PÁGINA DEL CARRITO ---
@login_required
def cart_view(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    return render(request, 'cart.html', {'cart': cart})

# --- APIS PARA EDITAR/ELIMINAR (AJAX) ---
@login_required
def api_update_cart_item(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        item_id = data.get('item_id')
        action = data.get('action') # 'increase' o 'decrease'
        
        item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        
        if action == 'increase':
            item.quantity += 1
        elif action == 'decrease':
            item.quantity -= 1
            if item.quantity < 1:
                item.quantity = 1 # No eliminar aquí, solo bajar a 1
        
        item.save()
        
        # Recalcular totales
        cart = item.cart
        return JsonResponse({
            'status': 'ok', 
            'item_total': item.get_cost(),
            'cart_total': cart.get_total(),
            'item_qty': item.quantity
        })
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def api_remove_cart_item(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        item_id = data.get('item_id')

        item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        cart = item.cart
        item.delete()

        return JsonResponse({
            'status': 'ok',
            'cart_total': cart.get_total(),
            'cart_count': cart.items.count()
        })
    return JsonResponse({'status': 'error'}, status=400)


# =================================================================================
# BULK UPLOAD VIEWS - Carga masiva de productos con IA
# =================================================================================

@login_required
@user_passes_test(lambda u: u.is_staff)
def bulk_upload_view(request):
    """
    Vista para carga masiva de productos.
    Procesamiento SÍNCRONO (sin Celery) para compatibilidad con PythonAnywhere.
    """
    if request.method == 'POST':
        form = BulkUploadForm(request.POST)
        files = request.FILES.getlist('files')

        if not files:
            messages.error(request, 'No se seleccionaron archivos.')
            return redirect('bulk_upload')

        if len(files) > 50:
            messages.error(request, f'Máximo 50 archivos. Seleccionaste {len(files)}.')
            return redirect('bulk_upload')

        if not form.is_valid():
            messages.error(request, 'Debes seleccionar el tipo de producto.')
            return redirect('bulk_upload')

        # Obtener el tipo de producto seleccionado
        product_type = form.cleaned_data['product_type']

        # Crear batch
        batch = BulkUploadBatch.objects.create(
            created_by=request.user,
            total_files=len(files),
            status='processing'
        )

        # Procesar archivos SÍNCRONAMENTE
        from .tasks import process_single_upload_item
        from django.utils import timezone

        for uploaded_file in files:
            item = BulkUploadItem.objects.create(
                batch=batch,
                original_filename=uploaded_file.name,
                source_file=uploaded_file,
                status='processing'
            )

            try:
                # Procesar directamente pasando el tipo de producto
                process_single_upload_item(item, product_type)
                batch.processed_files += 1
                batch.successful_uploads += 1
                batch.save()
            except Exception as e:
                item.status = 'failed'
                item.error_message = str(e)
                item.save()
                batch.processed_files += 1
                batch.failed_uploads += 1
                batch.error_log += f"\n{uploaded_file.name}: {str(e)}"
                batch.save()

        # Marcar batch como completado
        batch.status = 'completed'
        batch.save()

        messages.success(
            request,
            f'Procesamiento completado: {batch.successful_uploads} exitosos, '
            f'{batch.failed_uploads} fallidos de {batch.total_files} archivos.'
        )
        return redirect('bulk_upload_status', batch_id=batch.id)

    # GET: Mostrar formulario y lotes recientes
    form = BulkUploadForm()
    recent_batches = BulkUploadBatch.objects.filter(
        created_by=request.user
    ).order_by('-created_at')[:10]

    return render(request, 'dashboard/products/bulk_upload.html', {
        'form': form,
        'recent_batches': recent_batches
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def bulk_upload_status_view(request, batch_id):
    """
    Vista para ver el progreso de un lote de carga masiva.
    Soporta AJAX polling para actualizar progreso.
    """
    batch = get_object_or_404(BulkUploadBatch, id=batch_id)

    # Si es AJAX, retornar JSON con progreso
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': batch.status,
            'progress': batch.get_progress_percentage(),
            'processed': batch.processed_files,
            'total': batch.total_files,
            'successful': batch.successful_uploads,
            'failed': batch.failed_uploads,
        })

    # Vista normal con template
    items = batch.items.all().order_by('-created_at')

    return render(request, 'dashboard/products/bulk_upload_status.html', {
        'batch': batch,
        'items': items
    })


# =================================================================================
# ENHANCED PRODUCT MANAGEMENT - Lista mejorada con paginación y filtros
# =================================================================================

@login_required
@user_passes_test(lambda u: u.is_staff)
def product_list_enhanced_view(request):
    """
    Lista mejorada de productos con:
    - Paginación (20 por página)
    - Búsqueda por nombre/descripción
    - Filtros por categoría, tipo, estado online/offline
    - Ordenamiento
    - Checkboxes para acciones masivas
    """
    products = Product.objects.all().prefetch_related('categories', 'variants')

    # Búsqueda
    search_query = request.GET.get('q', '')
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Filtro por categoría
    category_id = request.GET.get('category')
    if category_id:
        products = products.filter(categories__id=category_id)

    # Filtro por tipo de producto
    product_type = request.GET.get('type')
    if product_type:
        products = products.filter(product_type=product_type)

    # Filtro por estado online/offline
    online_status = request.GET.get('online')
    if online_status == '1':
        products = products.filter(is_online=True)
    elif online_status == '0':
        products = products.filter(is_online=False)

    # Ordenamiento
    sort_by = request.GET.get('sort', '-created_at')
    products = products.order_by(sort_by)

    # Paginación (20 por página)
    paginator = Paginator(products.distinct(), 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'categories': Category.objects.all(),
        'product_types': Product.TYPE_CHOICES,
        'search_query': search_query,
        'current_category': category_id,
        'current_type': product_type,
        'current_online': online_status,
        'current_sort': sort_by,
    }

    # Si es petición AJAX, devolver solo la tabla y paginación
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'dashboard/products/partials/product_list_results.html', context)

    return render(request, 'dashboard/products/list_enhanced.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff)
def mass_edit_products_view(request):
    """
    Vista para editar múltiples productos a la vez.
    Soporta:
    - Agregar/Quitar/Reemplazar categorías
    - Poner online/offline
    - Eliminar productos
    """
    if request.method == 'POST':
        product_ids = request.POST.getlist('selected_products')
        action = request.POST.get('action')

        print(f"[Mass Edit] Products: {product_ids}, Action: {action}")  # Debug

        if not product_ids:
            messages.error(request, 'No has seleccionado ningún producto.')
            return redirect('panel_product_list')

        if not action:
            messages.error(request, 'No se seleccionó ninguna acción.')
            return redirect('panel_product_list')

        products = Product.objects.filter(id__in=product_ids)
        count = products.count()

        # Acciones que NO requieren categorías
        if action == 'set_online':
            products.update(is_online=True)
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'ok', 'message': f'✓ {count} producto(s) ahora están EN LÍNEA.'})
            messages.success(request, f'✓ {count} producto(s) ahora están EN LÍNEA.')
            return redirect('panel_product_list')

        elif action == 'set_offline':
            products.update(is_online=False)
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'ok', 'message': f'✓ {count} producto(s) ahora están FUERA DE LÍNEA.'})
            messages.success(request, f'✓ {count} producto(s) ahora están FUERA DE LÍNEA.')
            return redirect('panel_product_list')

        elif action == 'delete_products':
            product_names = [p.name for p in products[:5]]  # Primeros 5
            products.delete()
            msg = f'✓ {count} producto(s) eliminado(s): {", ".join(product_names)}{"..." if count > 5 else ""}'
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'ok', 'message': msg})
            messages.success(request, msg)
            return redirect('panel_product_list')

        # Acciones que requieren datos adicionales (mostrar formulario o procesar)
        elif action in ['add_categories', 'remove_categories', 'replace_categories', 'change_type', 'change_description']:
            # Si venimos del dropdown principal (solo acción, sin datos), mostrar el formulario
            if 'categories' not in request.POST and 'product_type' not in request.POST and 'description' not in request.POST:
                form = MassEditForm(initial={'action': action})
                return render(request, 'dashboard/products/mass_edit.html', {
                    'form': form,
                    'products': products,
                    'action': action,
                    'product_ids': product_ids
                })

            # Si ya enviamos el formulario de mass_edit.html, procesar los datos
            form = MassEditForm(request.POST)
            if form.is_valid():
                cat_ids = form.cleaned_data.get('categories')
                new_type = form.cleaned_data.get('product_type')
                new_desc = form.cleaned_data.get('description')

                if action == 'add_categories':
                    for product in products:
                        product.categories.add(*cat_ids)
                    messages.success(request, f'✓ Categorías agregadas a {count} producto(s).')

                elif action == 'remove_categories':
                    for product in products:
                        product.categories.remove(*cat_ids)
                    messages.success(request, f'✓ Categorías removidas de {count} producto(s).')

                elif action == 'replace_categories':
                    for product in products:
                        product.categories.clear()
                        product.categories.add(*cat_ids)
                    messages.success(request, f'✓ Categorías reemplazadas en {count} producto(s).')

                elif action == 'change_type':
                    products.update(product_type=new_type)
                    # Forzar regeneración de variantes si es necesario (opcional)
                    messages.success(request, f'✓ Tipo de producto cambiado en {count} productos.')

                elif action == 'change_description':
                    products.update(description=new_desc)
                    messages.success(request, f'✓ Descripción actualizada en {count} producto(s).')

                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'ok', 'message': 'Acción completada.'})
                return redirect('panel_product_list')
            else:
                # Si el formulario no es válido, volver a mostrarlo con errores
                return render(request, 'dashboard/products/mass_edit.html', {
                    'form': form,
                    'products': products,
                    'action': action,
                    'product_ids': product_ids
                })

        else:
            messages.error(request, f'Acción no reconocida: {action}')
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': f'Acción no reconocida: {action}'}, status=400)
            return redirect('panel_product_list')
    
    # Respuesta para acciones completadas en AJAX
    if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        # Re-renderizar la lista actualizada para devolverla en el JSON?
        # O simplemente decir OK y que el frontend recarge.
        # Vamos a devolver un mensaje y status OK.
        return JsonResponse({'status': 'ok', 'message': 'Acción completada con éxito.'})

    # GET request - mostrar formulario (no debería llegar aquí normalmente)
    messages.error(request, 'Método no permitido.')
    return redirect('panel_product_list')


@login_required
@user_passes_test(lambda u: u.is_staff)
def inline_edit_product_api(request):
    """
    API AJAX para edición inline (rápida):
    - Cambiar nombre del producto
    - Toggle estado online/offline
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        product_id = data.get('product_id')
        field = data.get('field')
        value = data.get('value')

        product = get_object_or_404(Product, id=product_id)

        if field == 'name':
            product.name = value
            product.save()
            return JsonResponse({'status': 'ok', 'new_value': value})

        elif field == 'is_online':
            product.is_online = bool(value)
            product.save()
            return JsonResponse({'status': 'ok', 'new_value': value})
            
        elif field == 'description':
            product.description = value
            product.save()
            return JsonResponse({'status': 'ok', 'new_value': value})

        elif field == 'categories':
            # value debe ser una lista de IDs [1, 2, 5]
            categories = Category.objects.filter(id__in=value)
            product.categories.set(categories)
            
            # Devolver nombres para actualizar la UI
            names = [{"id": c.id, "name": c.name} for c in categories]
            return JsonResponse({'status': 'ok', 'new_value': names})

        return JsonResponse({'status': 'error', 'message': 'Campo no válido'}, status=400)

    return JsonResponse({'status': 'error'}, status=400)