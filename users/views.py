from django.shortcuts import render, redirect
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
    from products.models import Order, Product, ShippingAddress
    from contabilidad.models import Transaction
    from django.db.models import Sum
    from django.utils import timezone
    from datetime import datetime
    
    # 1. Fechas para el mes actual
    now = timezone.now()
    month_start = datetime(now.year, now.month, 1).date()
    
    # 2. Consultas de Pedidos (Ventas Directas)
    orders_month = Order.objects.filter(created_at__date__gte=month_start)
    sales_orders = orders_month.aggregate(total=Sum('total'))['total'] or 0
    orders_count_month = orders_month.count()
    
    # 3. Consultas de Contabilidad (Otros Ingresos)
    accounting_incomes = Transaction.objects.filter(
        category__transaction_type='ingreso',
        date__gte=month_start
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    # Total Ventas = Pedidos + Ingresos Contabilidad
    total_sales_month = sales_orders + accounting_incomes
    
    active_clients = ShippingAddress.objects.values('phone').distinct().count()
    active_products = Product.objects.count()
    
    # 4. Pedidos Recientes (Últimos 5) con datos pre-procesados
    raw_recent_orders = Order.objects.select_related('status', 'address', 'user').order_by('-created_at')[:5]
    processed_orders = []
    
    for o in raw_recent_orders:
        client_name = "Cliente General"
        if o.address and o.address.full_name:
            client_name = o.address.full_name
        elif o.user:
            client_name = o.user.get_full_name() or o.user.email
            
        initials = (client_name[:2] if client_name else "??").upper()
        
        processed_orders.append({
            'id': o.id,
            'client_name': client_name,
            'initials': initials,
            'items_count': o.items.count(),
            'total': o.total,
            'status_name': o.status.name if o.status else "Pendiente",
            'status_color': o.status.color if o.status else "#6c757d",
        })

    context = {
        'total_sales_month': total_sales_month,
        'orders_count_month': orders_count_month,
        'active_clients': active_clients,
        'active_products': active_products,
        'recent_orders': processed_orders
    }
    return render(request, 'dashboard/home.html', context)

@login_required
def dashboard_pedidos_view(request):
    return render(request, 'dashboard/pedidos.html')

@login_required
def dashboard_tareas_view(request):
    return render(request, 'dashboard/tareas.html')

@login_required
def quick_client_create_view(request):
    """
    Crea un usuario rápido con rol de CUSTOMER desde la contabilidad u otras partes del panel.
    """
    if request.method == 'POST':
        from .models import User
        from django.contrib import messages
        from django.utils.crypto import get_random_string
        
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        
        if not name or not phone:
            messages.error(request, "El nombre y el teléfono son obligatorios.")
        else:
            # Verificar si ya existe un usuario con ese teléfono
            existing = User.objects.filter(phone_number=phone).first()
            if existing:
                messages.warning(request, f"Ya existe un cliente con el teléfono {phone}: {existing.get_full_name()}")
            else:
                # Si no hay email, generar uno dummy
                if not email:
                    email = f"{phone}@jema.local"
                
                # Crear el usuario
                random_pass = get_random_string(8)
                new_user = User.objects.create_user(
                    username=phone, # Usamos el teléfono como username para que sea único
                    email=email,
                    password=random_pass,
                    first_name=name,
                    phone_number=phone,
                    role=User.Role.CUSTOMER
                )
                messages.success(request, f"✅ Cliente {name} creado exitosamente.")
                
                # Si tiene un parámetro 'next', redirigir allí
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('accounting_transaction_create')
                
    return render(request, 'dashboard/quick_client_form.html')
