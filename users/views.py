from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView

# --- VISTAS PÚBLICAS ---

def home_view(request):
    # Simulamos productos destacados para que el carrusel no salga vacío
    featured_products = [
        {'name': 'Smart Watch Pro', 'price': 199.99, 'category': 'Electrónica', 'image': 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400', 'rating': 5, 'discount': 20},
        {'name': 'Kit Skincare', 'price': 89.99, 'category': 'Belleza', 'image': 'https://images.unsplash.com/photo-1585386959984-a4155224a1ad?w=400', 'rating': 4, 'reviews': 89},
        {'name': 'Audífonos Wireless', 'price': 149.99, 'category': 'Audio', 'image': 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400', 'rating': 5, 'reviews': 256, 'discount': 15},
        {'name': 'Running Shoes', 'price': 129.99, 'category': 'Deportes', 'image': 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400', 'rating': 4, 'reviews': 167},
    ]
    return render(request, 'index.html', {'featured_products': featured_products})

def catalogo_view(request):
    # Simulamos una lista de productos
    products = [
        {'name': 'Smart Watch Pro', 'price': 199.99, 'category': 'Electrónica', 'image': 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400', 'rating': 5, 'reviews': 128, 'discount': 20},
        {'name': 'Cámara Polaroid', 'price': 79.99, 'category': 'Fotografía', 'image': 'https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=400', 'rating': 5, 'reviews': 92},
        {'name': 'Gafas de Sol', 'price': 59.99, 'category': 'Accesorios', 'image': 'https://images.unsplash.com/photo-1560343090-f0409e92791a?w=400', 'rating': 4, 'reviews': 54},
        # Puedes duplicar estos diccionarios para ver más items
    ] * 3 
    return render(request, 'catalogo.html', {'products': products})

# --- VISTAS PRIVADAS (DASHBOARD) ---

@login_required
def dashboard_home_view(request):
    return render(request, 'dashboard/home.html')

@login_required
def dashboard_pedidos_view(request):
    return render(request, 'dashboard/pedidos.html')

@login_required
def dashboard_tareas_view(request):
    return render(request, 'dashboard/tareas.html')