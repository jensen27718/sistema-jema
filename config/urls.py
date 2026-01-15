from django.contrib import admin
from django.urls import path, include
# --- IMPORTACIONES NUEVAS ---
from django.conf import settings
from django.conf.urls.static import static

from users import views
from products import views as views_products
from products import catalog_views as views_catalogs
from products import internal_order_views as views_internal_orders  # Pedidos internos

urlpatterns = [
    path('admin-django/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    
    # Rutas Públicas
    path('', views.home_view, name='home'),
    path('catalogo/', views_products.catalogo_publico_view, name='catalogo'),
    path('catalogo/<slug:category_slug>/', views_products.catalogo_publico_view, name='catalogo_category'),
    
    # Rutas Dashboard General
    path('panel/', views.dashboard_home_view, name='panel_home'),
    path('panel/pedidos/', views.dashboard_pedidos_view, name='panel_pedidos'),
    path('panel/tareas/', views.dashboard_tareas_view, name='panel_tareas'),
    path('panel/clientes/nuevo-rapido/', views.quick_client_create_view, name='quick_client_create'),
    # --- RUTA DE CONTABILIDAD ---
    path('panel/contabilidad/', include('contabilidad.urls')),

    # --- RUTAS DE PRODUCTOS (CORREGIDAS) ---
    # Quitamos los dos puntos ':' y usamos guión bajo '_'
    path('panel/productos/', views_products.product_list_enhanced_view, name='panel_product_list'),  # Reemplazada con vista mejorada
    path('panel/productos/crear/', views_products.product_create_view, name='panel_product_create'),
    path('panel/productos/editar/<int:product_id>/', views_products.product_update_view, name='panel_product_update'),
    path('panel/productos/eliminar/<int:product_id>/', views_products.product_delete_view, name='panel_product_delete'),
    path('panel/productos/variantes/<int:product_id>/', views_products.product_variants_view, name='panel_product_variants'),

    # --- RUTAS DE CARGA MASIVA ---
    path('panel/productos/bulk-upload/', views_products.bulk_upload_view, name='bulk_upload'),
    path('panel/productos/bulk-upload/status/<int:batch_id>/', views_products.bulk_upload_status_view, name='bulk_upload_status'),

    # --- RUTAS DE EDICIÓN MASIVA ---
    path('panel/productos/mass-edit/', views_products.mass_edit_products_view, name='mass_edit_products'),

    # --- API PARA EDICIÓN INLINE ---
    path('api/products/inline-edit/', views_products.inline_edit_product_api, name='inline_edit_product'),


    # --- RUTAS DE CATEGORÍAS (NUEVAS) ---
    path('panel/categorias/', views_products.category_list_view, name='panel_category_list'),
    path('panel/categorias/crear/', views_products.category_create_view, name='panel_category_create'),
    path('panel/categorias/editar/<int:category_id>/', views_products.category_update_view, name='panel_category_update'),
    path('panel/categorias/eliminar/<int:category_id>/', views_products.category_delete_view, name='panel_category_delete'),

    # --- RUTAS DE CARRITO (NUEVAS) ---
    path('api/add-to-cart/', views_products.add_to_cart_api, name='api_add_to_cart'),
    path('carrito/', views_products.cart_view, name='cart_view'),
    path('api/cart/update/', views_products.api_update_cart_item, name='api_update_cart'),
    path('api/cart/remove/', views_products.api_remove_cart_item, name='api_remove_cart'),
    
    # --- RUTAS DE ESTADOS (NUEVAS) ---
    path('panel/estados/', views_products.status_list_view, name='panel_status_list'),
    path('panel/estados/crear/', views_products.status_create_view, name='panel_status_create'),
    path('panel/estados/editar/<int:status_id>/', views_products.status_update_view, name='panel_status_update'),
    path('panel/estados/eliminar/<int:status_id>/', views_products.status_delete_view, name='panel_status_delete'),

    # --- RUTAS DE PEDIDOS (ADMIN) ---
    path('panel/ordenes/', views_products.panel_orders_list_view, name='panel_pedidos'), # Reemplaza el placeholder
    path('panel/ordenes/<int:order_id>/', views_products.panel_order_detail_view, name='panel_order_detail'),

    # --- RUTAS DE CARRITOS (ADMIN) ---
    path('panel/carritos/', views_products.panel_cart_list_view, name='panel_cart_list'),
    path('panel/carritos/<int:cart_id>/', views_products.panel_cart_detail_view, name='panel_cart_detail'),

    # --- RUTAS DE CLIENTES (CRUD) ---
    path('panel/clientes/', views.client_list_view, name='client_list'),
    path('panel/clientes/editar/<int:user_id>/', views.client_update_view, name='client_update'),
    path('panel/clientes/eliminar/<int:user_id>/', views.client_delete_view, name='client_delete'),

    # --- RUTAS DE CATÁLOGOS PDF (NUEVAS) ---
    path('panel/catalogos/', views_catalogs.catalog_selection_view, name='catalog_selection'),
    path('panel/catalogos/generar/', views_catalogs.generate_catalog_pdf_view, name='generate_catalog_pdf'),

    # === RUTAS DE PEDIDOS INTERNOS (DRAG & DROP) ===
    path('panel/pedidos-internos/', views_internal_orders.internal_orders_list_view, name='internal_orders_list'),
    path('panel/pedidos-internos/crear/', views_internal_orders.internal_order_create_view, name='internal_order_create'),
    path('panel/pedidos-internos/<int:order_id>/', views_internal_orders.internal_order_detail_view, name='internal_order_detail'),
    path('panel/pedidos-internos/<int:order_id>/editar/', views_internal_orders.internal_order_edit_view, name='internal_order_edit'),
    path('panel/pedidos-internos/<int:order_id>/eliminar/', views_internal_orders.internal_order_delete_view, name='internal_order_delete'),
    path('panel/pedidos-internos/<int:order_id>/confirmar/', views_internal_orders.internal_order_confirm_view, name='internal_order_confirm'),
    path('panel/pedidos-internos/<int:order_id>/estado/', views_internal_orders.internal_order_update_status_view, name='internal_order_update_status'),

    # === APIs AJAX PARA PEDIDOS INTERNOS ===
    path('api/internal-orders/filter-variants/', views_internal_orders.api_filter_variants, name='api_filter_variants'),
    path('api/internal-orders/get-filters/', views_internal_orders.api_get_available_filters, name='api_get_available_filters'),
    path('api/internal-orders/add-item/', views_internal_orders.api_internal_order_add_item, name='api_add_item'),
    path('api/internal-orders/remove-item/', views_internal_orders.api_internal_order_remove_item, name='api_remove_item'),
    path('api/internal-orders/update-quantity/', views_internal_orders.api_internal_order_update_qty, name='api_update_qty'),
    path('api/internal-orders/auto-select/', views_internal_orders.api_internal_order_auto_select, name='api_auto_select'),
    path('api/internal-orders/clear/', views_internal_orders.api_internal_order_clear, name='api_clear_order'),
    path('api/internal-orders/update-info/', views_internal_orders.api_internal_order_update_info, name='api_update_order_info'),

    # ...
    path('checkout/', views_products.checkout_process_view, name='checkout_process'),
    path('direccion/nueva/', views_products.address_create_view, name='address_create'),
    path('pedido/<int:order_id>/', views_products.order_detail_view, name='order_detail'),
    
]
# --- AGREGA ESTO AL FINAL DEL ARCHIVO ---
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


