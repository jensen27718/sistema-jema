from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView
from products.models import Product
# --- VISTAS PÚBLICAS ---

def home_view(request):
    # Traer los últimos 4 productos subidos (Recién llegados)
    featured_products = Product.objects.filter(image__isnull=False).order_by('-created_at')[:4]
    
    return render(request, 'index.html', {'featured_products': featured_products})



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