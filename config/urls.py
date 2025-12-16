from django.contrib import admin
from django.urls import path, include
from users import views

urlpatterns = [
    path('admin-django/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    
    # Rutas Públicas
    path('', views.home_view, name='home'),
    path('catalogo/', views.catalogo_view, name='catalogo'),
    
    # Rutas del Dashboard (Nombres corregidos, sin dos puntos)
    path('panel/', views.dashboard_home_view, name='panel_home'),
    path('panel/pedidos/', views.dashboard_pedidos_view, name='panel_pedidos'),
    path('panel/tareas/', views.dashboard_tareas_view, name='panel_tareas'),
]