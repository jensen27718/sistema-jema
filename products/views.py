from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
# Importa TANTO Product COMO Category
from .models import Product, Category, ProductVariant
from .forms import ProductForm, CategoryForm
from .services import generar_variantes_vinilo, generar_variantes_impresos # <--- Importamos la magia
from django.db.models import Min


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


def catalogo_publico_view(request):
    # Traemos los productos y calculamos el precio mínimo de sus variantes
    products = Product.objects.annotate(
        min_price=Min('variants__price')
    ).filter(
        variants__isnull=False # Solo mostrar productos que tengan variantes (precios)
    ).distinct()

    # Filtros básicos (Categoría)
    categoria_slug = request.GET.get('categoria')
    if categoria_slug:
        products = products.filter(category__slug=categoria_slug)

    context = {
        'products': products,
        'categories': Category.objects.all() # Para el filtro lateral
    }
    return render(request, 'catalogo.html', context)

# --- CRUD PRODUCTOS EXTRA ---

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