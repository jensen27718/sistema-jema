import os
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.template.loader import get_template
from django.contrib.auth.decorators import login_required, user_passes_test
from xhtml2pdf import pisa
from io import BytesIO
from .models import Product, Category

def is_staff(user):
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(is_staff)
def catalog_selection_view(request):
    categories = Category.objects.all()
    product_types = Product.TYPE_CHOICES
    return render(request, 'dashboard/catalogs/selection.html', {
        'categories': categories,
        'product_types': product_types
    })

@login_required
@user_passes_test(is_staff)
def generate_catalog_pdf_view(request):
    # Obtener parámetros del POST
    catalog_name = request.POST.get('catalog_name', 'Catálogo de Productos')
    product_type = request.POST.get('product_type')
    category_ids = request.POST.getlist('categories')
    phone = request.POST.get('phone', '321 216 5252')
    
    # Iniciar query de productos
    products = Product.objects.all()
    
    if product_type:
        products = products.filter(product_type=product_type)
        
    if category_ids:
        products = products.filter(category_id__in=category_ids)
        
    products = products.order_by('name')
    
    # Obtener el label legible del tipo
    type_label = "General"
    if product_type:
        type_label = dict(Product.TYPE_CHOICES).get(product_type, "General")

    # Preparar el contexto para el template
    context = {
        'catalog_name': catalog_name,
        'catalog_type': type_label,
        'phone': phone,
        'products': products,
        'logo_url': os.path.join(settings.BASE_DIR, 'static', 'img', 'logo_jema.png'), # Ajustar si es necesario
        'media_root': settings.MEDIA_ROOT,
        'base_dir': settings.BASE_DIR,
    }
    
    # Renderizar HTML a PDF
    template = get_template('dashboard/catalogs/pdf_template.html')
    html = template.render(context)
    
    result = BytesIO()
    def link_callback(uri, rel):
        """
        Convert HTML URIs to absolute system paths so xhtml2pdf can access those
        resources on local disk.
        """
        # Si es una URL completa (como S3), la devolvemos tal cual para que xhtml2pdf intente descargarla
        if uri.startswith('http://') or uri.startswith('https://'):
            return uri
            
        # Si es una ruta de media
        if uri.startswith(settings.MEDIA_URL) and settings.MEDIA_URL != '/':
            path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
        elif uri.startswith(settings.STATIC_URL):
            path = os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, ""))
        else:
            # Intentar resolver como ruta absoluta
            path = os.path.join(settings.BASE_DIR, uri.lstrip('/'))
            
        return path

    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result, link_callback=link_callback)
    
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        filename = f"Catalogo_{catalog_name.replace(' ', '_')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    return HttpResponse("Error generando el PDF", status=500)
