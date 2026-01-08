"""
Formularios para carga masiva y edición masiva de productos
"""
from django import forms
from django.core.exceptions import ValidationError
from .models import Category, Product
import os


class BulkUploadForm(forms.Form):
    """
    Formulario para subir múltiples archivos PDF/PNG en lote.
    """
    product_type = forms.ChoiceField(
        label='Tipo de Producto',
        choices=Product.TYPE_CHOICES,
        initial='vinilo_corte',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Todos los archivos se crearán con este tipo de producto',
        required=True
    )


class MassEditForm(forms.Form):
    """
    Formulario para editar múltiples productos a la vez.
    Permite agregar, quitar o reemplazar categorías y cambiar estado online/offline.
    """
    ACTION_CHOICES = [
        ('', '-- Seleccionar Acción --'),
        ('add_categories', 'Agregar Categorías'),
        ('remove_categories', 'Quitar Categorías'),
        ('replace_categories', 'Reemplazar Categorías'),
        ('set_online', 'Poner En Línea'),
        ('set_offline', 'Poner Fuera de Línea'),
        ('change_type', 'Cambiar Tipo de Producto'),
        ('change_description', 'Cambiar Descripción'),
    ]

    action = forms.ChoiceField(
        label='Acción',
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True
    )

    categories = forms.ModelMultipleChoiceField(
        label='Categorías',
        queryset=Category.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        help_text='Selecciona una o más categorías'
    )

    product_type = forms.ChoiceField(
        label='Tipo de Producto',
        choices=[('', '---')] + list(Product.TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    description = forms.CharField(
        label='Nueva Descripción',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        help_text='Se aplicará a todos los productos seleccionados.'
    )

    def clean(self):
        """
        Validación personalizada para asegurar que:
        - Si la acción requiere categorías, se seleccionaron
        - Si la acción requiere tipo de producto, se seleccionó
        """
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        categories = cleaned_data.get('categories')
        product_type = cleaned_data.get('product_type')

        # Acciones que requieren categorías
        category_actions = ['add_categories', 'remove_categories', 'replace_categories']
        if action in category_actions and not categories:
            raise ValidationError(
                f'La acción "{dict(self.ACTION_CHOICES)[action]}" requiere seleccionar al menos una categoría'
            )

        # Acción que requiere tipo de producto
        if action == 'change_type' and not product_type:
            raise ValidationError('Debes seleccionar un tipo de producto')

        # Acción que requiere descripción
        if action == 'change_description' and not cleaned_data.get('description'):
            raise ValidationError('Debes escribir una descripción para aplicar el cambio masivo')

        return cleaned_data


class ProductFilterForm(forms.Form):
    """
    Formulario para filtrar productos en la lista mejorada.
    """
    q = forms.CharField(
        label='Buscar',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por nombre o descripción...'
        })
    )

    category = forms.ModelChoiceField(
        label='Categoría',
        queryset=Category.objects.all(),
        required=False,
        empty_label='Todas las categorías',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    product_type = forms.ChoiceField(
        label='Tipo de Producto',
        choices=[('', 'Todos los tipos')] + list(Product.TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    ONLINE_CHOICES = [
        ('', 'Todos'),
        ('1', 'En Línea'),
        ('0', 'Fuera de Línea'),
    ]

    online = forms.ChoiceField(
        label='Estado',
        choices=ONLINE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    SORT_CHOICES = [
        ('-created_at', 'Más recientes'),
        ('created_at', 'Más antiguos'),
        ('name', 'Nombre (A-Z)'),
        ('-name', 'Nombre (Z-A)'),
    ]

    sort = forms.ChoiceField(
        label='Ordenar por',
        choices=SORT_CHOICES,
        required=False,
        initial='-created_at',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
