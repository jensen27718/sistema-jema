from django.urls import path
from . import views

urlpatterns = [
    path('', views.accounting_dashboard_view, name='accounting_dashboard'),
    path('movimientos/', views.transaction_list_view, name='accounting_transaction_list'),
    path('nuevo/', views.transaction_create_view, name='accounting_transaction_create'),
    path('editar/<int:transaction_id>/', views.transaction_update_view, name='accounting_transaction_update'),
    path('eliminar/<int:transaction_id>/', views.transaction_delete_view, name='accounting_transaction_delete'),
    # Cuentas
    path('cuentas/nueva/', views.account_create_view, name='accounting_account_create'),
    path('cuentas/<int:account_id>/', views.account_detail_view, name='accounting_account_detail'),
    path('cuentas/editar/<int:account_id>/', views.account_update_view, name='accounting_account_update'),
    # Categorías
    path('categorias/', views.category_list_view, name='accounting_category_list'),
    path('categorias/nueva/', views.category_create_view, name='accounting_category_create'),
    path('categorias/editar/<int:category_id>/', views.category_update_view, name='accounting_category_update'),
    path('categorias/eliminar/<int:category_id>/', views.category_delete_view, name='accounting_category_delete'),
    # Proveedores
    path('proveedores/', views.provider_list_view, name='accounting_provider_list'),
    path('proveedores/nuevo/', views.provider_create_view, name='accounting_provider_create'),
    path('proveedores/editar/<int:provider_id>/', views.provider_update_view, name='accounting_provider_update'),
    path('proveedores/eliminar/<int:provider_id>/', views.provider_delete_view, name='accounting_provider_delete'),
    # Deudas
    path('deudas/', views.debt_list_view, name='accounting_debt_list'),
    path('deudas/nueva/', views.debt_create_view, name='accounting_debt_create'),
    path('deudas/<int:debt_id>/', views.debt_detail_view, name='accounting_debt_detail'),
    path('deudas/<int:debt_id>/abonar/', views.payment_create_view, name='accounting_payment_create'),
    # Facturas
    path('facturas/', views.invoice_list_view, name='invoice_list'),
    path('facturas/nueva/', views.invoice_create_view, name='invoice_create'),
    path('facturas/<int:invoice_id>/', views.invoice_detail_view, name='invoice_detail'),
    path('facturas/<int:invoice_id>/eliminar/', views.invoice_delete_view, name='invoice_delete'),
    path('facturas/api/cliente/<int:client_id>/', views.api_client_address, name='api_client_address'),
    # Guías de Envío
    path('guias/', views.guide_list_view, name='guide_list'),
    path('guias/nueva/', views.guide_create_view, name='guide_create'),
    path('guias/imprimir/', views.guide_print_view, name='guide_print'),
    path('guias/<int:guide_id>/', views.guide_detail_view, name='guide_detail'),
    path('guias/<int:guide_id>/eliminar/', views.guide_delete_view, name='guide_delete'),
    path('guias/api/cliente/<int:client_id>/', views.api_guide_client_data, name='api_guide_client_data'),
    path('guias/api/observaciones/', views.api_observations, name='api_observations'),
    path('guias/api/buscar-clientes/', views.api_search_clients, name='api_search_clients'),
]
