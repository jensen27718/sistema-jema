from django import forms
from django.core.exceptions import ValidationError
from .models import Product, Category # <--- Asegúrate de importar Category
from .models import ShippingAddress

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
ALLOWED_SOURCE_TYPES = ALLOWED_IMAGE_TYPES + ['application/pdf']

class AddressForm(forms.ModelForm):
    class Meta:
        model = ShippingAddress
        fields = ['full_name', 'phone', 'department', 'city', 'neighborhood', 'address_line']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre quien recibe'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'type': 'tel', 'placeholder': 'Celular'}),
            'department': forms.Select(attrs={'class': 'form-select', 'id': 'dept-select'}),
            'city': forms.Select(attrs={'class': 'form-select', 'id': 'city-select'}),
            'neighborhood': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del barrio'}),
            'address_line': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Calle, Carrera, #Casa...'}),
        }



class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'categories', 'product_type', 'description', 'source_file', 'image', 'is_online', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'categories': forms.CheckboxSelectMultiple(),  # Soporte para múltiples categorías
            'product_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'source_file': forms.FileInput(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'is_online': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'categories': 'Categorías (selecciona una o más)',
            'is_online': 'Visible en Catálogo Público',
            'is_active': 'Producto Activo',
        }
        help_texts = {
            'categories': 'El producto aparecerá en todas las categorías seleccionadas',
            'is_active': 'Si se desactiva, no aparecerá en ningún lado.',
        }

    def clean_image(self):
        f = self.cleaned_data.get('image')
        if f and hasattr(f, 'size'):
            if f.size > MAX_FILE_SIZE:
                raise ValidationError("La imagen no puede superar 50MB.")
            if hasattr(f, 'content_type') and f.content_type not in ALLOWED_IMAGE_TYPES:
                raise ValidationError("Solo se permiten imágenes JPG, PNG, WebP o GIF.")
        return f

    def clean_source_file(self):
        f = self.cleaned_data.get('source_file')
        if f and hasattr(f, 'size'):
            if f.size > MAX_FILE_SIZE:
                raise ValidationError("El archivo fuente no puede superar 50MB.")
            if hasattr(f, 'content_type') and f.content_type not in ALLOWED_SOURCE_TYPES:
                raise ValidationError("Solo se permiten archivos PDF, JPG, PNG, WebP o GIF.")
        return f
   



class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'icon']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Cumpleaños'}),
            'icon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: bi-star'}),
        }
        help_texts = {
            'icon': 'Usa nombres de iconos Bootstrap (ej: bi-heart, bi-star, bi-tag)',
        }