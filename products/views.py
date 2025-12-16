from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
# Importa TANTO Product COMO Category
from .models import Product, Category, ProductVariant
from .forms import ProductForm, CategoryForm
from .services import generar_variantes_vinilo # <--- Importamos la magia



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
            
            # --- AQUÍ OCURRE LA AUTOMATIZACIÓN ---
            if product.product_type == 'vinilo_corte':
                try:
                    count = generar_variantes_vinilo(product)
                    messages.success(request, f"Producto creado con éxito. Se generaron {count} variantes de precios automáticamente.")
                except Exception as e:
                    messages.warning(request, f"Producto creado, pero hubo un error generando precios: {e}")
            
            return redirect('panel_product_list')
    else:
        form = ProductForm()
    
    return render(request, 'dashboard/products/form.html', {'form': form})



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