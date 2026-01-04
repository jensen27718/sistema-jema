from django.urls import path
from . import views

urlpatterns = [
    path('', views.accounting_dashboard_view, name='accounting_dashboard'),
    path('nuevo/', views.transaction_create_view, name='accounting_transaction_create'),
    # Cuentas
    path('cuentas/nueva/', views.account_create_view, name='accounting_account_create'),
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
]
