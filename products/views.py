from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
# Importa TANTO Product COMO Category
from .models import Product, Category, ProductVariant,Cart, CartItem
from .forms import ProductForm, CategoryForm
from .services import generar_variantes_vinilo, generar_variantes_impresos # <--- Importamos la magia
from django.db.models import Min
import json  # <--- AGREGAR ESTA LÍNEA
from django.http import JsonResponse
from django.core.serializers import serialize
from django.core.serializers.json import DjangoJSONEncoder

import urllib.parse # <--- AGREGAR ARRIBA
from .models import ShippingAddress, Order, OrderItem, OrderStatus # <--- IMPORTAR NUEVOS MODELOS
from .forms import AddressForm # <--- IMPORTAR FORM

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
            
            return redirect('panel_product_list')
            
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


def catalogo_publico_view(request, category_slug=None):
    # 1. Obtener productos base
    products = Product.objects.filter(variants__isnull=False).distinct().order_by('-created_at')
    
    # 2. Filtrar por categoría si existe el slug
    current_category = None
    if category_slug:
        current_category = get_object_or_404(Category, slug=category_slug)
        products = products.filter(category=current_category)

    # 3. Obtener todas las categorías para el menú
    categories = Category.objects.all()
    
    # --- AUTO-FIX: Asegurar que todas las categorías tengan slug ---
    # Esto corrige el error "NoReverseMatch" si existen categorías antiguas sin slug
    for cat in categories:
        if not cat.slug:
            try:
                cat.save() # El método save() del modelo genera el slug automáticamente
            except:
                pass # Si falla (ej: duplicado), lo ignoramos por ahora para no romper la web

    # 4. Construir JSON de variantes para el Frontend (Magia para que sea rápido)
    variants_data = {}
    for product in products:
        p_variants = product.variants.all()
        variants_data[product.id] = []
        for v in p_variants:
            variants_data[product.id].append({
                'id': v.id,
                'size_id': v.size.id,
                'size_name': v.size.name,
                'material_id': v.material.id, # Para diferenciar vinilo de mailan
                'color_name': v.color.name if v.color else "Estándar", # AGREGAR ESTO
                'material_name': v.material.name,  
                'color_id': v.color.id if v.color else None,
                'price': float(v.price),
                'stock': v.stock
            })

    context = {
        'products': products,
        'categories': categories,
        'current_category': current_category,
        'variants_json': json.dumps(variants_data, cls=DjangoJSONEncoder)
    }
    return render(request, 'catalogo_tiktok.html', context) # Usaremos una plantilla nueva

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
            return redirect('panel_product_list')
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