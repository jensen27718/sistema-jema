from django.contrib import admin
from django.urls import path, include
# --- IMPORTACIONES NUEVAS ---
from django.conf import settings
from django.conf.urls.static import static

from users import views
from products import views as views_products # Asegúrate de importar esto

urlpatterns = [
    path('admin-django/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    
    # Rutas Públicas
    path('', views.home_view, name='home'),
    path('catalogo/', views_products.catalogo_publico_view, name='catalogo'),
    
    # Rutas Dashboard General
    path('panel/', views.dashboard_home_view, name='panel_home'),
    path('panel/pedidos/', views.dashboard_pedidos_view, name='panel_pedidos'),
    path('panel/tareas/', views.dashboard_tareas_view, name='panel_tareas'),

    # --- RUTAS DE PRODUCTOS (CORREGIDAS) ---
    # Quitamos los dos puntos ':' y usamos guión bajo '_'
    path('panel/productos/', views_products.product_list_view, name='panel_product_list'),
    path('panel/productos/crear/', views_products.product_create_view, name='panel_product_create'),
    path('panel/productos/editar/<int:product_id>/', views_products.product_update_view, name='panel_product_update'),
    path('panel/productos/eliminar/<int:product_id>/', views_products.product_delete_view, name='panel_product_delete'),
    path('panel/productos/variantes/<int:product_id>/', views_products.product_variants_view, name='panel_product_variants'),


    # --- RUTAS DE CATEGORÍAS (NUEVAS) ---
    path('panel/categorias/', views_products.category_list_view, name='panel_category_list'),
    path('panel/categorias/crear/', views_products.category_create_view, name='panel_category_create'),
    path('panel/categorias/editar/<int:category_id>/', views_products.category_update_view, name='panel_category_update'),
    path('panel/categorias/eliminar/<int:category_id>/', views_products.category_delete_view, name='panel_category_delete'),

    # --- RUTAS DE CARRITO (NUEVAS) ---
    path('api/add-to-cart/', views_products.add_to_cart_api, name='api_add_to_cart'),
    
]
# --- AGREGA ESTO AL FINAL DEL ARCHIVO ---
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


